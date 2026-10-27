#!/usr/bin/env python3

"""Build the pynng CFFI interface.

Uses headerkit's libclang backend to parse NNG C headers into an IR,
then converts the IR to CFFI cdef strings.

This module serves dual purposes:
  1. Build-time: executed by cffi_buildtool to generate CFFI bindings
  2. Test-time: imported by tests to verify generate_cdef() and _extract_defines()

When imported as a regular Python module (e.g., by tests), only the functions
and constants are made available. The ffibuilder setup only runs when executed
by cffi_buildtool (which sets __name__ to "gen-cffi-src") or directly.

Supports generating bindings for both nng v1 and v2. The target module is
controlled by the NNG_MODULE_NAME environment variable:
  - "pynng._nng" (default): v1 bindings using NNG_V1_HEADERS
  - "pynng._nng_v2": v2 bindings using NNG_V2_HEADERS
"""

import glob
import logging
import os
import re
import subprocess
import sys


def _transform_headerkit_clang_source(path: str, text: str) -> str:
    """Adapt headerkit._clang source files to work around PyPy ctypes incompatibilities."""
    if path.endswith("cindex.py"):
        # 1. Bind _compat_c_interop_string before FUNCTION_LIST is populated at import time.
        text = text.replace(
            "class c_interop_string(c_char_p):",
            "from headerkit._clang import _compat_c_interop_string as c_interop_string\n"
            "class _unused_c_interop_string:",
        )
        text = text.replace(
            'return b.decode("utf8")',
            "return (None if not (ptr := c_void_p.value.__get__(x) if isinstance(x, c_void_p)"
            " else getattr(x, 'value', None)) else ctypes.string_at(ptr).decode('utf8'))",
        )
        # 2. Copy callback struct/pointer arguments off the C stack before storing in Python lists.
        text = text.replace(
            "child._tu = self._tu",
            "child = Cursor.from_buffer_copy(child); child._tu = self._tu",
        )
        text = text.replace(
            "field._tu = self._tu",
            "field = Cursor.from_buffer_copy(field); field._tu = self._tu",
        )
        text = text.replace(
            "base._tu = self._tu",
            "base = Cursor.from_buffer_copy(base); base._tu = self._tu",
        )
        text = text.replace(
            "method._tu = self._tu",
            "method = Cursor.from_buffer_copy(method); method._tu = self._tu",
        )
        text = text.replace(
            "loc = lptr.contents",
            "loc = SourceLocation.from_buffer_copy(lptr.contents)",
        )
        text = text.replace(
            "File(fobj)",
            "File(c_object_p.from_buffer_copy(fobj))",
        )
        # 3. libclang's clang_equalCursors mutates X.data[1] = 0 in place; under ARM64 AAPCS64
        # PyPy's _rawffi passes self._buffer by pointer without copying, clobbering Cursor state.
        text = text.replace(
            "conf.lib.clang_equalCursors(self, other)",
            "conf.lib.clang_equalCursors("
            "Cursor.from_buffer_copy(self), Cursor.from_buffer_copy(other))",
        )
    return text


if sys.implementation.name == "pypy":
    import importlib.abc

    class _PyPyHeaderkitClangLoader(importlib.abc.SourceLoader):
        """SourceLoader that adapts headerkit._clang's ctypes bindings for PyPy."""

        def __init__(self, fullname: str, path: str) -> None:
            self.fullname = fullname
            self.path = path

        def get_filename(self, fullname: str) -> str:
            return self.path

        def get_data(self, path: str | bytes) -> bytes:
            with open(path, "rb") as f:
                data = f.read()
            text = _transform_headerkit_clang_source(str(path), data.decode("utf-8"))
            return text.encode("utf-8")

        def get_code(self, fullname: str):
            source = self.get_data(self.path)
            return compile(source, self.path, "exec", dont_inherit=True)

    class _PyPyHeaderkitClangFinder(importlib.abc.MetaPathFinder):
        def find_spec(self, fullname, path, target=None):
            if fullname == "headerkit._clang" or fullname.startswith(
                "headerkit._clang."
            ):
                for finder in sys.meta_path:
                    if isinstance(finder, _PyPyHeaderkitClangFinder):
                        continue
                    find_spec = getattr(finder, "find_spec", None)
                    if find_spec is None:
                        continue
                    spec = find_spec(fullname, path, target)
                    if spec is not None and spec.origin and spec.origin.endswith(".py"):
                        spec.loader = _PyPyHeaderkitClangLoader(fullname, spec.origin)
                        return spec
            return None

    sys.meta_path.insert(0, _PyPyHeaderkitClangFinder())

from headerkit.backends import get_backend
from headerkit.writers.cffi import header_to_cffi

try:
    from headerkit.cache import is_up_to_date, save_hash
    from headerkit.writers import get_writer

    _CACHE_AVAILABLE = True
except ImportError:
    _CACHE_AVAILABLE = False

logger = logging.getLogger(__name__)

# v1 headers: individual protocol headers plus TLS
NNG_V1_HEADERS = [
    "nng/nng.h",
    "nng/protocol/bus0/bus.h",
    "nng/protocol/pair0/pair.h",
    "nng/protocol/pair1/pair.h",
    "nng/protocol/pipeline0/push.h",
    "nng/protocol/pipeline0/pull.h",
    "nng/protocol/pubsub0/pub.h",
    "nng/protocol/pubsub0/sub.h",
    "nng/protocol/reqrep0/req.h",
    "nng/protocol/reqrep0/rep.h",
    "nng/protocol/survey0/survey.h",
    "nng/protocol/survey0/respond.h",
    "nng/supplemental/tls/tls.h",
    "nng/transport/tls/tls.h",
]

# v2 consolidates all public API into a single header
NNG_V2_HEADERS = [
    "nng/nng.h",
]

# Keep NNG_HEADERS as alias for v1 (backward compatibility)
NNG_HEADERS = NNG_V1_HEADERS

EXCLUDE_PATTERNS = [r"nng_tls_config_(pass|key)", r"NNG_PROTOCOL_NUMBER"]

# Additional patterns to exclude when TLS is disabled (PYNNG_TLS_ENABLED=0).
# nng_tls_config_psk exists only when a TLS engine is compiled in.
EXCLUDE_PATTERNS_NO_TLS = [r"nng_tls_config_psk"]

# v2 has additional opaque types (forward-declared structs with no public
# definition) that CFFI cannot handle as concrete types. Exclude them and
# all functions that reference them. Also exclude nng_id_map and related
# functions (internal data structure not needed by pynng).
EXCLUDE_PATTERNS_V2 = [
    r"nng_tls_config_(pass|key)",
    r"NNG_PROTOCOL_NUMBER",
    r"nng_id_map",
    r"nng_id_(get|set|alloc|remove|visit)",
    r"nng_tls_cert",
    r"nng_pipe_peer_cert",
    r"nng_stream_peer_cert",
    # Functions declared in v2 headers but not implemented in the library.
    # These cause LNK2019 on Windows (MSVC requires all symbols resolved).
    r"nng_ctx_set$",  # nng_ctx_set (generic) removed; typed variants remain
    r"nng_dialer_get_addr$",  # removed; nng_dialer_set_addr still exists
    r"_uint64$",  # uint64 typed accessors not implemented in v2
]

# Path for the cached cdef file (placed next to build_pynng.py).
_SCRIPT_DIR = os.path.dirname(
    os.path.abspath(
        __file__ if "__file__" in dir() else os.path.join(os.getcwd(), "build_pynng.py")
    )
)
_SRC_DIR = os.path.join(_SCRIPT_DIR, "src")
_AIO_ENGINE_H = os.path.join(_SRC_DIR, "aio_engine.h")

# CFFI cdef declarations for the pure C AIO completion engine (aio_engine.h).
_AIO_ENGINE_CDEF = """
        typedef struct pynng_aio_entry pynng_aio_entry_t;
        typedef struct pynng_mpsc_queue pynng_mpsc_queue_t;

        pynng_mpsc_queue_t *pynng_mpsc_queue_new(int write_fd);
        void pynng_mpsc_queue_close(pynng_mpsc_queue_t *q);
        void pynng_mpsc_queue_free(pynng_mpsc_queue_t *q);
        pynng_aio_entry_t *pynng_aio_entry_new(void *aio, uintptr_t slot_id, pynng_mpsc_queue_t *q);
        void pynng_aio_entry_set_slot_id(pynng_aio_entry_t *e, uintptr_t slot_id);
        int pynng_aio_entry_is_idle(pynng_aio_entry_t *e);
        void pynng_aio_entry_free(pynng_aio_entry_t *e);
        void pynng_native_aio_complete(void *arg);
        int pynng_mpsc_drain_batch(pynng_mpsc_queue_t *q, uintptr_t *out_slot_ids, int max_entries);
"""


def _validate_nng_include_dir(path: str) -> str | None:
    """Return path if it contains nng/nng.h, else None."""
    if os.path.isfile(os.path.join(path, "nng", "nng.h")):
        return path
    return None


def _detect_env_var() -> str | None:
    """Strategy 1: NNG_INCLUDE_DIR environment variable."""
    val = os.environ.get("NNG_INCLUDE_DIR")
    if val:
        result = _validate_nng_include_dir(val)
        if result:
            logger.debug("NNG headers found via NNG_INCLUDE_DIR env var: %s", result)
        else:
            logger.debug("NNG_INCLUDE_DIR set to %s but nng/nng.h not found there", val)
        return result
    return None


def _detect_build_tree() -> str | None:
    """Strategy 2: scikit-build-core FetchContent build cache."""
    project_root = os.path.dirname(os.path.abspath(__file__))
    candidates = glob.glob(
        os.path.join(project_root, "build", "*", "_deps", "nng-src", "include")
    )
    for candidate in candidates:
        result = _validate_nng_include_dir(candidate)
        if result:
            logger.debug("NNG headers found in build tree: %s", result)
            return result
    return None


def _detect_pkg_config() -> str | None:
    """Strategy 3: pkg-config --cflags nng."""
    try:
        output = subprocess.run(
            ["pkg-config", "--cflags", "nng"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if output.returncode == 0:
            for flag in output.stdout.strip().split():
                if flag.startswith("-I"):
                    path = flag[2:]
                    result = _validate_nng_include_dir(path)
                    if result:
                        logger.debug("NNG headers found via pkg-config: %s", result)
                        return result
    except (FileNotFoundError, subprocess.TimeoutExpired):
        logger.debug("pkg-config not available or timed out")
    return None


def _detect_system_paths() -> str | None:
    """Strategy 4: Common system include paths."""
    paths = ["/usr/include", "/usr/local/include"]
    for path in paths:
        result = _validate_nng_include_dir(path)
        if result:
            logger.debug("NNG headers found in system path: %s", result)
            return result
    return None


def _detect_homebrew() -> str | None:
    """Strategy 5: macOS Homebrew."""
    if sys.platform != "darwin":
        return None
    try:
        output = subprocess.run(
            ["brew", "--prefix", "nng"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if output.returncode == 0:
            prefix = output.stdout.strip()
            include_path = os.path.join(prefix, "include")
            result = _validate_nng_include_dir(include_path)
            if result:
                logger.debug("NNG headers found via Homebrew: %s", result)
                return result
    except (FileNotFoundError, subprocess.TimeoutExpired):
        logger.debug("brew command not available or timed out")

    # Fallback: check common Homebrew prefix paths directly
    for prefix in ["/opt/homebrew", "/usr/local"]:
        include_path = os.path.join(prefix, "include")
        result = _validate_nng_include_dir(include_path)
        if result:
            logger.debug("NNG headers found in Homebrew prefix: %s", result)
            return result
    return None


def _detect_macports() -> str | None:
    """Strategy 6: macOS MacPorts."""
    if sys.platform != "darwin":
        return None
    result = _validate_nng_include_dir("/opt/local/include")
    if result:
        logger.debug("NNG headers found via MacPorts: %s", result)
    return result


def find_nng_include_dir() -> str | None:
    """Auto-detect the NNG include directory using a cascade of strategies.

    Tries the following in order, returning the first valid path found:
      1. NNG_INCLUDE_DIR environment variable
      2. Build tree (scikit-build-core FetchContent cache)
      3. pkg-config
      4. Common system include paths (/usr/include, /usr/local/include)
      5. macOS Homebrew (brew --prefix nng, then common prefixes)
      6. macOS MacPorts (/opt/local/include)

    Each candidate is validated by checking for the existence of nng/nng.h.

    Returns:
        The path to the NNG include directory, or None if not found.
    """
    strategies = [
        ("env_var", _detect_env_var),
        ("build_tree", _detect_build_tree),
        ("pkg_config", _detect_pkg_config),
        ("system_paths", _detect_system_paths),
        ("homebrew", _detect_homebrew),
        ("macports", _detect_macports),
    ]
    for name, strategy in strategies:
        result = strategy()
        if result is not None:
            return result
        logger.debug("Strategy '%s' did not find NNG headers", name)
    logger.debug("No NNG headers found by any strategy")
    return None


def _get_nng_include_dir() -> str:
    """Detect the NNG include directory.

    Uses the auto-detection cascade (env var, build tree, pkg-config,
    system paths, Homebrew, MacPorts).

    Raises:
        RuntimeError: If NNG headers cannot be found by any strategy.
    """
    include_dir = find_nng_include_dir()
    if include_dir is None:
        raise RuntimeError(
            "Cannot find NNG headers. Set NNG_INCLUDE_DIR environment "
            "variable, install NNG development headers, or build first. "
            "During cmake builds, NNG_INCLUDE_DIR is set automatically."
        )
    return include_dir


_CDEF_MEMO: dict[
    tuple[tuple[tuple[str, float], ...], str, tuple[str, ...]], tuple[str, list[str]]
] = {}


def generate_cdef(
    headers=None, include_dir=None, exclude_patterns=None
) -> tuple[str, list[str]]:
    """Parse NNG headers and generate CFFI cdef declarations.

    Args:
        headers: List of header paths relative to the include dir.
            Defaults to NNG_V1_HEADERS.
        include_dir: Override for NNG include directory.
            If None, uses auto-detection (NNG_INCLUDE_DIR env var, etc.).
        exclude_patterns: Regex patterns for symbols to exclude.
            Defaults to EXCLUDE_PATTERNS.

    Returns:
        A tuple of (cdef_string, existing_headers) where existing_headers
        is the filtered list of headers that exist on disk.
    """
    if headers is None:
        headers = NNG_V1_HEADERS
    if exclude_patterns is None:
        exclude_patterns = EXCLUDE_PATTERNS
    if include_dir is None:
        include_dir = _get_nng_include_dir()

    # Determine cache file if using standard header configurations
    cache_path = None
    if headers == NNG_V1_HEADERS and exclude_patterns == EXCLUDE_PATTERNS:
        cache_path = os.path.join(_SCRIPT_DIR, "_nng_cdef_cache.txt")
    elif headers == NNG_V2_HEADERS and exclude_patterns == EXCLUDE_PATTERNS_V2:
        cache_path = os.path.join(_SCRIPT_DIR, "_nng_v2_cdef_cache.txt")

    existing = [h for h in headers if os.path.exists(os.path.join(include_dir, h))]
    header_paths = [os.path.join(include_dir, h) for h in existing]
    memo_key = (
        tuple((h, os.path.getmtime(p)) for h, p in zip(existing, header_paths)),
        include_dir,
        tuple(exclude_patterns),
    )
    if memo_key in _CDEF_MEMO:
        cached_cdef, cached_existing = _CDEF_MEMO[memo_key]
        return cached_cdef, list(cached_existing)
    build_script = os.path.join(_SCRIPT_DIR, "build_pynng.py")

    # Check cache freshness
    if _CACHE_AVAILABLE and cache_path:
        try:
            fresh = is_up_to_date(
                output_path=cache_path,
                header_paths=header_paths,
                writer_name="cffi",
                extra_inputs=[build_script],
            )
        except Exception:
            fresh = False

        if fresh and os.path.exists(cache_path):
            with open(cache_path) as f:
                cdef = f.read()
            return cdef, existing

    # Build umbrella header that includes all existing NNG headers
    includes = "\n".join(f"#include <{h}>" for h in existing)
    umbrella = f"""\
#define NNG_DECL
#define NNG_STATIC_LIB
#define NNG_DEPRECATED
{includes}
"""

    # Parse with headerkit libclang backend (umbrella.h already includes all
    # target headers and project_prefixes=(include_dir,) extracts declarations
    # from all of them in a single TranslationUnit pass).
    backend = get_backend("libclang")
    header = backend.parse(
        umbrella,
        "umbrella.h",
        include_dirs=[include_dir],
        project_prefixes=(include_dir,),
        recursive_includes=False,
    )

    # Convert IR to CFFI cdef string
    cdef = header_to_cffi(header, exclude_patterns=exclude_patterns)

    # Fix anonymous enums: nng.h defines `typedef enum { ... } nng_pipe_ev;`
    # and `typedef enum { ... } nng_err;` without a tag name, so `enum nng_pipe_ev`
    # and `enum nng_err` are incomplete types in C.
    cdef = re.sub(r"\benum\s+nng_pipe_ev\b", "nng_pipe_ev", cdef)
    cdef = re.sub(r"\benum\s+nng_err\b", "nng_err", cdef)

    # In nng.h v2, nng_init_params is an anonymous struct typedef.
    # Replace parameter type with void * so CFFI doesn't require the full struct definition
    # (pynng only passes NULL to nng_init).
    cdef = re.sub(r"\bconst\s+(?:struct\s+)?nng_init_params\s*\*", "void *", cdef)
    cdef = re.sub(r"\b(?:struct\s+)?nng_init_params\s*\*", "void *", cdef)

    # Extract additional #define constants from nng.h via regex
    # (libclang can miss macro values that involve expressions)
    nng_h_path = os.path.join(include_dir, "nng/nng.h")
    extra_defines = _extract_defines(nng_h_path)
    if extra_defines:
        cdef = cdef + "\n" + extra_defines

    # Write cdef to cache file and save hash
    if _CACHE_AVAILABLE and cache_path:
        try:
            with open(cache_path, "w") as f:
                f.write(cdef)
            save_hash(
                output_path=cache_path,
                header_paths=header_paths,
                writer_name="cffi",
                extra_inputs=[build_script],
                writer=get_writer("cffi"),
            )
        except Exception as exc:
            logger.debug("Failed to save cdef cache: %s", exc)

    _CDEF_MEMO[memo_key] = (cdef, list(existing))
    return cdef, existing


def _extract_defines(nng_h_path: str) -> str:
    """Extract #define constants from nng.h that libclang may not capture."""
    with open(nng_h_path) as f:
        content = f.read()

    defines = []
    for m in re.finditer(
        r"^#define\s+(NNG_FLAG_\w+|NNG_\w+_VERSION|NNG_MAXADDRLEN)\b",
        content,
        re.MULTILINE,
    ):
        name = m.group(1)
        defines.append(f"#define {name} ...")

    return "\n".join(defines)


def _build_ffi(module_name="pynng._nng", headers=None, exclude_patterns=None):
    """Set up the CFFI ffibuilder for use by cffi_buildtool.

    Args:
        module_name: CFFI module name. "pynng._nng" for v1, "pynng._nng_v2" for v2.
        headers: Header list to parse. Defaults based on module_name.
        exclude_patterns: Regex patterns for symbols to exclude.
            Defaults based on module_name.

    This is called at module level only during builds (cffi_buildtool or
    direct execution), never when imported by tests.
    """
    from cffi import FFI

    # Default headers and exclude patterns based on module name
    if headers is None:
        if module_name == "pynng._nng_v2":
            headers = NNG_V2_HEADERS
        else:
            headers = NNG_V1_HEADERS
    if exclude_patterns is None:
        if module_name == "pynng._nng_v2":
            exclude_patterns = list(EXCLUDE_PATTERNS_V2)
        else:
            exclude_patterns = list(EXCLUDE_PATTERNS)

    # When TLS is disabled, exclude additional symbols that only exist
    # when a TLS engine is compiled in.
    if os.environ.get("PYNNG_TLS_ENABLED") == "0":
        exclude_patterns = list(exclude_patterns) + EXCLUDE_PATTERNS_NO_TLS

    nng_include_dir = _get_nng_include_dir()

    # Generate cdef content and get the list of existing headers
    cdef_content, existing_headers = generate_cdef(
        headers=headers,
        include_dir=nng_include_dir,
        exclude_patterns=exclude_patterns,
    )

    callbacks = f"""
        extern "Python" void _async_complete(void *);
        extern "Python" void _nng_pipe_cb(nng_pipe, nng_pipe_ev, void *);
{_AIO_ENGINE_CDEF}
    """

    ffi = FFI()

    # Build set_source includes from the existing headers returned by generate_cdef()
    source_includes = "\n".join(f"        #include <{h}>" for h in existing_headers)

    include_dirs = [nng_include_dir]
    if os.path.isdir(_SRC_DIR):
        include_dirs.append(_SRC_DIR)

    ffi.set_source(
        module_name,
        f"""
            #define NNG_DECL
            #define NNG_STATIC_LIB
{source_includes}
            /* nng.h declares typedef enum {{ ... }} nng_pipe_ev and nng_err anonymously
               without tags. CFFI emits sizeof(enum ...); define tags to make them complete. */
            enum nng_pipe_ev {{ _nng_pipe_ev_dummy = 0 }};
            enum nng_err {{ _nng_err_dummy = 0 }};

            #include "aio_engine.h"
        """,
        include_dirs=include_dirs,
    )

    ffi.cdef(cdef_content + callbacks)
    return ffi


# Only run the build when executed by cffi_buildtool (sets __name__ to
# "gen-cffi-src") or when run directly as a script. When imported normally
# by tests (__name__ == "build_pynng"), skip the build setup.
if __name__ in ("gen-cffi-src", "__main__"):
    # Check NNG_MODULE_NAME env var to determine which module to build.
    # Default is v1 ("pynng._nng").
    _module_name = os.environ.get("NNG_MODULE_NAME", "pynng._nng")
    ffibuilder = _build_ffi(module_name=_module_name)

    if __name__ == "__main__":
        ffibuilder.compile(verbose=True)
