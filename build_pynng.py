#!/usr/bin/env python3

"""Build the pynng CFFI interface.

Uses headerkit's libclang backend to parse nng C headers into an IR,
then converts the IR to CFFI cdef strings and PEP 484 .pyi stubs via
headerkit's CffiWriter and PyiWriter.

This module serves dual purposes:
  1. Build-time: executed by cffi_buildtool to generate CFFI bindings
  2. Test-time: imported by tests to verify generate_cdef() and generate_pyi()

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
import subprocess
import sys
from typing import Any

try:
    from headerkit.backends import get_backend
    from headerkit.writers.cffi import CffiWriter
    from headerkit.writers.pyi import PyiWriter

    _HAS_HEADERKIT = True
except ImportError:
    get_backend = None  # type: ignore[assignment]
    CffiWriter = None  # type: ignore[assignment,misc]
    PyiWriter = None  # type: ignore[assignment,misc]
    _HAS_HEADERKIT = False


def _require_headerkit() -> None:
    """Ensure headerkit is importable before parsing headers or generating bindings."""
    if not _HAS_HEADERKIT or get_backend is None:
        raise RuntimeError(
            "headerkit (requires Python >= 3.11) is required to parse nng "
            "headers and generate CFFI bindings from source. On Python 3.10, "
            "install a pre-built pynng wheel instead of building from source."
        )


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

# Repository root and native C source directory paths.
_BUILD_SCRIPT = os.path.abspath(
    __file__ if "__file__" in dir() else os.path.join(os.getcwd(), "build_pynng.py")
)
_SCRIPT_DIR = os.path.dirname(_BUILD_SCRIPT)
_SRC_DIR = os.path.join(_SCRIPT_DIR, "src")
_AIO_ENGINE_H = os.path.join(_SRC_DIR, "aio_engine.h")


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
            logger.debug("nng headers found via NNG_INCLUDE_DIR env var: %s", result)
        else:
            logger.debug("NNG_INCLUDE_DIR set to %s but nng/nng.h not found there", val)
        return result
    return None


def _detect_build_tree() -> str | None:
    """Strategy 2: scikit-build-core FetchContent build cache."""
    project_root = _SCRIPT_DIR
    candidates = glob.glob(
        os.path.join(project_root, "build", "*", "_deps", "nng-src", "include")
    )
    for candidate in candidates:
        result = _validate_nng_include_dir(candidate)
        if result:
            logger.debug("nng headers found in build tree: %s", result)
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
            check=False,
        )
        if output.returncode == 0:
            for flag in output.stdout.strip().split():
                if flag.startswith("-I"):
                    path = flag[2:]
                    result = _validate_nng_include_dir(path)
                    if result:
                        logger.debug("nng headers found via pkg-config: %s", result)
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
            logger.debug("nng headers found in system path: %s", result)
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
            check=False,
        )
        if output.returncode == 0:
            prefix = output.stdout.strip()
            include_path = os.path.join(prefix, "include")
            result = _validate_nng_include_dir(include_path)
            if result:
                logger.debug("nng headers found via Homebrew: %s", result)
                return result
    except (FileNotFoundError, subprocess.TimeoutExpired):
        logger.debug("brew command not available or timed out")

    # Fallback: check common Homebrew prefix paths directly
    for prefix in ["/opt/homebrew", "/usr/local"]:
        include_path = os.path.join(prefix, "include")
        result = _validate_nng_include_dir(include_path)
        if result:
            logger.debug("nng headers found in Homebrew prefix: %s", result)
            return result
    return None


def _detect_macports() -> str | None:
    """Strategy 6: macOS MacPorts."""
    if sys.platform != "darwin":
        return None
    result = _validate_nng_include_dir("/opt/local/include")
    if result:
        logger.debug("nng headers found via MacPorts: %s", result)
    return result


def find_nng_include_dir() -> str | None:
    """Auto-detect the nng include directory using a cascade of strategies.

    Tries the following in order, returning the first valid path found:
      1. NNG_INCLUDE_DIR environment variable
      2. Build tree (scikit-build-core FetchContent cache)
      3. pkg-config
      4. Common system include paths (/usr/include, /usr/local/include)
      5. macOS Homebrew (brew --prefix nng, then common prefixes)
      6. macOS MacPorts (/opt/local/include)

    Each candidate is validated by checking for the existence of nng/nng.h.

    Returns:
        The path to the nng include directory, or None if not found.
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
        logger.debug("Strategy '%s' did not find nng headers", name)
    logger.debug("No nng headers found by any strategy")
    return None


def _get_nng_include_dir() -> str:
    """Detect the nng include directory.

    Uses the auto-detection cascade (env var, build tree, pkg-config,
    system paths, Homebrew, MacPorts).

    Raises:
        RuntimeError: If nng headers cannot be found by any strategy.
    """
    include_dir = find_nng_include_dir()
    if include_dir is None:
        raise RuntimeError(
            "Cannot find nng headers. Set NNG_INCLUDE_DIR environment "
            "variable, install nng development headers, or build first. "
            "During cmake builds, NNG_INCLUDE_DIR is set automatically."
        )
    return include_dir


DEFINE_PATTERNS = [
    r"^NNG_FLAG_\w+$",
    r"^NNG_\w+_VERSION$",
    r"^NNG_MAXADDRLEN$",
]

EXTERN_PYTHON_CALLBACKS = [
    "_async_complete",
    "_nng_pipe_cb",
]

_PARSE_MEMO: dict[
    tuple[tuple[tuple[str, float], ...], str], tuple[Any, list[str], str]
] = {}

_CDEF_MEMO: dict[
    tuple[tuple[tuple[str, float], ...], str, tuple[str, ...]], tuple[str, list[str]]
] = {}


def _parse_nng_headers(headers=None, include_dir=None):
    """Parse nng and aio_engine headers into a headerkit Header IR (memoized by mtimes)."""
    _require_headerkit()
    if headers is None:
        headers = NNG_V1_HEADERS
    if include_dir is None:
        include_dir = _get_nng_include_dir()

    existing = [h for h in headers if os.path.exists(os.path.join(include_dir, h))]
    aio_mtime = (
        os.path.getmtime(_AIO_ENGINE_H) if os.path.exists(_AIO_ENGINE_H) else 0.0
    )
    build_mtime = (
        os.path.getmtime(_BUILD_SCRIPT) if os.path.exists(_BUILD_SCRIPT) else 0.0
    )
    parse_key = (
        tuple((h, os.path.getmtime(os.path.join(include_dir, h))) for h in existing)
        + (("_aio_engine_h", aio_mtime), ("_build_pynng_py", build_mtime)),
        include_dir,
    )
    if parse_key in _PARSE_MEMO:
        cached_header, cached_existing, cached_include_dir = _PARSE_MEMO[parse_key]
        return cached_header, list(cached_existing), cached_include_dir

    includes = "\n".join(f"#include <{h}>" for h in existing)
    umbrella = f"""\
#define NNG_DECL
#define NNG_STATIC_LIB
#define NNG_DEPRECATED
#define PYNNG_CFFI_CDEF
{includes}
#include "aio_engine.h"
"""
    backend = get_backend("libclang")
    header = backend.parse(
        umbrella,
        "umbrella.h",
        include_dirs=[include_dir, _SRC_DIR],
        project_prefixes=(include_dir, _SRC_DIR),
        recursive_includes=False,
    )
    _PARSE_MEMO[parse_key] = (header, list(existing), include_dir)
    return header, existing, include_dir


def generate_cdef(
    headers=None, include_dir=None, exclude_patterns=None
) -> tuple[str, list[str]]:
    """Parse nng headers and generate CFFI cdef declarations via headerkit.

    Args:
        headers: List of header paths relative to the include dir.
            Defaults to NNG_V1_HEADERS.
        include_dir: Override for nng include directory.
            If None, uses auto-detection (NNG_INCLUDE_DIR env var, etc.).
        exclude_patterns: Regex patterns for symbols to exclude.
            Defaults to EXCLUDE_PATTERNS.

    Returns:
        A tuple of (cdef_string, existing_headers) where existing_headers
        is the filtered list of headers that exist on disk.
    """
    _require_headerkit()
    if headers is None:
        headers = NNG_V1_HEADERS
    if exclude_patterns is None:
        exclude_patterns = EXCLUDE_PATTERNS
    if include_dir is None:
        include_dir = _get_nng_include_dir()

    existing = [h for h in headers if os.path.exists(os.path.join(include_dir, h))]
    header_paths = [os.path.join(include_dir, h) for h in existing]
    aio_mtime = (
        os.path.getmtime(_AIO_ENGINE_H) if os.path.exists(_AIO_ENGINE_H) else 0.0
    )
    build_mtime = (
        os.path.getmtime(_BUILD_SCRIPT) if os.path.exists(_BUILD_SCRIPT) else 0.0
    )
    memo_key = (
        tuple((h, os.path.getmtime(p)) for h, p in zip(existing, header_paths))
        + (("_aio_engine_h", aio_mtime), ("_build_pynng_py", build_mtime)),
        include_dir,
        tuple(exclude_patterns),
    )
    if memo_key in _CDEF_MEMO:
        cached_cdef, cached_existing = _CDEF_MEMO[memo_key]
        return cached_cdef, list(cached_existing)

    header, existing, _ = _parse_nng_headers(headers=headers, include_dir=include_dir)

    cdef_exclude = list(exclude_patterns) + [
        f"^{name}$" for name in EXTERN_PYTHON_CALLBACKS
    ]
    writer = CffiWriter(
        exclude_patterns=cdef_exclude,
        define_patterns=DEFINE_PATTERNS,
        extern_python=EXTERN_PYTHON_CALLBACKS,
    )
    cdef = writer.write(header)

    _CDEF_MEMO[memo_key] = (cdef, list(existing))
    return cdef, existing


def generate_pyi(
    headers=None,
    include_dir=None,
    exclude_patterns=None,
    *,
    tls_enabled: bool = True,
) -> str:
    """Parse nng headers and generate PEP 484 CFFI .pyi stub declarations."""
    _require_headerkit()
    if headers is None:
        headers = NNG_V1_HEADERS
    if exclude_patterns is None:
        if headers == NNG_V2_HEADERS:
            exclude_patterns = list(EXCLUDE_PATTERNS_V2)
        else:
            exclude_patterns = list(EXCLUDE_PATTERNS)
    if not tls_enabled:
        exclude_patterns = list(exclude_patterns) + EXCLUDE_PATTERNS_NO_TLS

    header, _, _ = _parse_nng_headers(headers=headers, include_dir=include_dir)
    writer = PyiWriter(
        mode="cffi",
        exclude_patterns=list(exclude_patterns),
        define_patterns=DEFINE_PATTERNS,
        extern_python=EXTERN_PYTHON_CALLBACKS,
    )
    return writer.write(header)


def _build_ffi(
    module_name="pynng._nng",
    headers=None,
    exclude_patterns=None,
    include_dir=None,
    *,
    tls_enabled: bool | None = None,
):
    """Set up the CFFI ffibuilder for use by cffi_buildtool.

    Args:
        module_name: CFFI module name. "pynng._nng" for v1, "pynng._nng_v2" for v2.
        headers: Header list to parse. Defaults based on module_name.
        exclude_patterns: Regex patterns for symbols to exclude.
            Defaults based on module_name.
        include_dir: Override for nng include directory.
        tls_enabled: Whether TLS symbols are enabled. Defaults to PYNNG_TLS_ENABLED env var.

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
    if tls_enabled is None:
        tls_enabled = os.environ.get("PYNNG_TLS_ENABLED") != "0"
    if not tls_enabled:
        exclude_patterns = list(exclude_patterns) + EXCLUDE_PATTERNS_NO_TLS

    nng_include_dir = include_dir if include_dir is not None else _get_nng_include_dir()

    # Generate cdef content and get the list of existing headers
    cdef_content, existing_headers = generate_cdef(
        headers=headers,
        include_dir=nng_include_dir,
        exclude_patterns=exclude_patterns,
    )

    # Emit PEP 484 typing stub for the compiled CFFI extension module.
    # Only overwrite an existing stub when TLS is enabled and the generated stub
    # is Any-free (headerkit >= 0.51.0), so partial builds with PYNNG_TLS_ENGINE=none
    # or older headerkit releases do not degrade the tracked stubs.
    stub_rel = module_name.replace(".", os.sep) + ".pyi"
    stub_path = os.path.join(_SCRIPT_DIR, stub_rel)
    if os.path.isdir(os.path.dirname(stub_path)) and (
        tls_enabled or not os.path.exists(stub_path)
    ):
        pyi_content = generate_pyi(
            headers=headers,
            include_dir=nng_include_dir,
            exclude_patterns=exclude_patterns,
        )
        if not os.path.exists(stub_path) or "from typing import Any" not in pyi_content:
            with open(stub_path, "w", encoding="utf-8") as f:
                f.write(pyi_content)

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
            #include "aio_engine.h"
        """,
        include_dirs=include_dirs,
    )

    ffi.cdef(cdef_content)
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
