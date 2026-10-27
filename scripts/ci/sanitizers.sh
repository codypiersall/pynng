#!/usr/bin/env bash
# Build nng v1, nng v2, the TLS library and the pynng cffi extensions with
# AddressSanitizer and UndefinedBehaviorSanitizer, then run the test suite
# under both. Any sanitizer report fails the run.
#
# Usage: scripts/ci/sanitizers.sh [pytest arguments]
#   With no arguments, runs the same test selection as the smoketest workflow.
#
# Environment:
#   CC                   C compiler (Linux: GCC; macOS: Apple clang)
#   SANITIZER_PYTHON     Python version or interpreter for the venv (default 3.12)
#   SANITIZER_BUILD_DIR  Build directory (default build/sanitizers)
#   CMAKE_ARGS           Extra CMake arguments, read by scikit-build-core
set -euo pipefail

repo=$(cd "$(dirname "$0")/../.." && pwd)
cd "$repo"

build_dir=${SANITIZER_BUILD_DIR:-$repo/build/sanitizers}
venv=$build_dir/venv
build_log=$build_dir/build.log
report_dir=$build_dir/reports
cc=${CC:-cc}

# UBSan errors are fatal, except nonnull-attribute: a fatal (no-recover)
# handler aborts even for a suppressed report, so the one check with an entry
# in ubsan.supp must stay recoverable. halt_on_error=1 in UBSAN_OPTIONS still
# stops on any unsuppressed nonnull-attribute report.
san_flags="-fsanitize=address,undefined -fno-sanitize-recover=undefined -fsanitize-recover=nonnull-attribute -fno-omit-frame-pointer -g"

# CFLAGS and LDFLAGS initialise CMAKE_C_FLAGS and the linker flags in every
# CMake configure, including the separate configure of the nng v2
# ExternalProject, which does not inherit flags from the top-level project.
export CC=$cc
export CFLAGS="$san_flags ${CFLAGS:-}"
export LDFLAGS="-fsanitize=address,undefined ${LDFLAGS:-}"

case $(uname -s) in
  Linux)
    if ! grep -q 'Free Software Foundation' <<<"$("$cc" --version)"; then
      echo "error: on Linux this script needs GCC (CC=$cc is not GCC)" >&2
      exit 1
    fi
    runtime=$("$cc" -print-file-name=libasan.so)
    ubsan_runtime=$("$cc" -print-file-name=libubsan.so)
    for f in "$runtime" "$ubsan_runtime"; do
      [ -f "$f" ] || { echo "error: sanitizer runtime not found: $f" >&2; exit 1; }
    done
    preload_var=LD_PRELOAD
    preload="$runtime:$ubsan_runtime"
    ;;
  Darwin)
    # The UBSan runtime is part of the ASan runtime on macOS. The system
    # Python is SIP-protected and drops DYLD_* variables, so use a uv-managed
    # interpreter.
    runtime=$("$cc" -print-file-name=libclang_rt.asan_osx_dynamic.dylib)
    [ -f "$runtime" ] || { echo "error: sanitizer runtime not found: $runtime" >&2; exit 1; }
    preload_var=DYLD_INSERT_LIBRARIES
    preload=$runtime
    # The runtime removes itself from DYLD_INSERT_LIBRARIES at start-up by
    # default; tests that start a child Python need it kept.
    platform_asan_options=strip_env=0:
    export UV_PYTHON_PREFERENCE=only-managed
    ;;
  *)
    echo "error: unsupported platform $(uname -s)" >&2
    exit 1
    ;;
esac

mkdir -p "$build_dir"
if [ ! -x "$venv/bin/python" ]; then
  uv venv --python "${SANITIZER_PYTHON:-3.12}" "$venv"
fi

echo "Building with CFLAGS=$CFLAGS (log: $build_log)"
uv pip install --python "$venv/bin/python" -v -e '.[dev]' \
  --reinstall-package pynng \
  -C build-dir="$build_dir/cmake" \
  >"$build_log" 2>&1 || { tail -n 100 "$build_log"; exit 1; }

# Check that the flags reached each artifact, not only the build log: an
# uninstrumented library still links and passes every test.
artifacts=(
  "$build_dir/cmake/_deps/nng-build/libnng.a"
  "$build_dir/cmake/nng_v2_install/lib/libnng.a"
)
while IFS= read -r so; do
  artifacts+=("$so")
done < <(find "$venv/lib" -path '*/pynng/_nng*.so')
if [ "${#artifacts[@]}" -ne 4 ]; then
  echo "error: expected the _nng and _nng_v2 extensions in $venv, found: ${artifacts[*]:2}" >&2
  exit 1
fi
for a in "${artifacts[@]}"; do
  [ -f "$a" ] || { echo "error: missing build artifact $a" >&2; exit 1; }
  # Read the whole symbol table first: with pipefail, grep -q closing the
  # pipe early makes nm fail with SIGPIPE.
  # The installed extensions are stripped (scikit-build-core strips on
  # install in a Release build), which removes the ELF .symtab that plain nm
  # reads. The sanitizer hooks stay in the dynamic symbol table as undefined
  # imports, so read that one on Linux. Mach-O keeps them in the one table.
  nm_args=()
  if [ "$(uname -s)" = Linux ] && [[ $a == *.so ]]; then
    nm_args=(--dynamic --undefined-only)
  fi
  syms=$(nm ${nm_args[@]+"${nm_args[@]}"} "$a" 2>/dev/null || true)
  for sym in __asan_report_ __ubsan_handle_; do
    if ! grep -q "$sym" <<<"$syms"; then
      echo "error: $a has no $sym references; it was built without sanitizers" >&2
      exit 1
    fi
  done
  echo "instrumented: $a"
done
echo "build log lines with -fsanitize: $(grep -c -- '-fsanitize=address,undefined' "$build_log")"

if [ $# -eq 0 ]; then
  set -- test --ignore=test/test_build.py --ignore=test/test_check_nng_updates.py
fi

rm -rf "$report_dir"
mkdir -p "$report_dir"

# detect_leaks=0: CPython does not free all of its objects at exit, and nng
# keeps global state until nng_fini(), so leak reports would come mostly from
# outside pynng. Leak detection needs a suppression list before it can gate.
# log_path sends each report to a file, so a report from a child process
# fails the run even when the test ignores that child's exit status.
export ASAN_OPTIONS="${platform_asan_options:-}detect_leaks=0:abort_on_error=1:halt_on_error=1:log_path=$report_dir/report${ASAN_OPTIONS:+:$ASAN_OPTIONS}"
export UBSAN_OPTIONS="print_stacktrace=1:halt_on_error=1:suppressions=$repo/scripts/ci/ubsan.supp:log_path=$report_dir/report${UBSAN_OPTIONS:+:$UBSAN_OPTIONS}"
# Route CPython allocations through malloc so ASan sees them.
export PYTHONMALLOC=malloc

# Exported here rather than passed through env(1): on macOS, a SIP-protected
# binary such as /usr/bin/env drops DYLD_* variables.
status=0
(export "$preload_var=$preload"; exec "$venv/bin/pytest" -rs "$@") || status=$?

if [ -n "$(ls -A "$report_dir")" ]; then
  for f in "$report_dir"/*; do
    echo "===== $f"
    cat "$f"
  done
  echo "error: sanitizer reports found" >&2
  [ "$status" -ne 0 ] || status=1
fi
exit "$status"
