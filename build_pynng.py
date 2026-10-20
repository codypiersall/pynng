#!/usr/bin/env python3

"""Build the pynng CFFI interface.

Uses headerkit's libclang backend to parse NNG C headers into an IR,
then converts the IR to CFFI cdef strings.  Supports caching via
headerkit.cache to skip expensive header parsing when inputs haven't changed.
"""

import os
import re

from headerkit.backends import get_backend
from cffi import FFI

from headerkit.writers.cffi import header_to_cffi

try:
    from headerkit.cache import is_up_to_date, save_hash
    from headerkit.writers import get_writer

    _CACHE_AVAILABLE = True
except ImportError:
    _CACHE_AVAILABLE = False

NNG_INCLUDE_DIR = os.environ.get("NNG_INCLUDE_DIR")
if NNG_INCLUDE_DIR is None:
    raise RuntimeError(
        "NNG_INCLUDE_DIR environment variable must be set. "
        "This is normally set by the CMake build system."
    )

NNG_HEADERS = [
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

EXCLUDE_PATTERNS = [r"nng_tls_config_(pass|key)", r"NNG_PROTOCOL_NUMBER"]

# Path for the cached cdef file (placed next to build_pynng.py).
# __file__ may not be defined when invoked via cffi_buildtool exec-python.
_SCRIPT_DIR = os.path.dirname(os.path.abspath(
    __file__ if "__file__" in dir() else os.path.join(os.getcwd(), "build_pynng.py")
))
CDEF_CACHE_PATH = os.path.join(_SCRIPT_DIR, "_nng_cdef_cache.txt")


def _get_header_paths(existing_headers: list[str]) -> list[str]:
    """Return absolute paths for existing NNG headers."""
    return [os.path.join(NNG_INCLUDE_DIR, h) for h in existing_headers]


def _existing_header_list() -> list[str]:
    """Return the filtered list of NNG_HEADERS that exist on disk."""
    return [
        h for h in NNG_HEADERS if os.path.exists(os.path.join(NNG_INCLUDE_DIR, h))
    ]


def generate_cdef() -> tuple[str, list[str]]:
    """Parse NNG headers and generate CFFI cdef declarations.

    Uses headerkit caching when available to skip expensive libclang parsing
    if the headers and build script haven't changed since the last run.

    Returns:
        A tuple of (cdef_string, existing_headers) where existing_headers
        is the filtered list of NNG_HEADERS that exist on disk.
    """
    existing = _existing_header_list()
    header_paths = _get_header_paths(existing)
    build_script = os.path.join(_SCRIPT_DIR, "build_pynng.py")

    # Check cache freshness
    if _CACHE_AVAILABLE:
        try:
            fresh = is_up_to_date(
                output_path=CDEF_CACHE_PATH,
                header_paths=header_paths,
                writer_name="cffi",
                extra_inputs=[build_script],
            )
        except Exception:
            fresh = False

        if fresh and os.path.exists(CDEF_CACHE_PATH):
            print("CFFI cdef cache hit, skipping header parsing")
            with open(CDEF_CACHE_PATH) as f:
                cdef = f.read()
            return cdef, existing

    print("CFFI cdef cache miss, parsing headers...")

    # Build umbrella header that includes all existing NNG headers
    includes = "\n".join(f"#include <{h}>" for h in existing)
    umbrella = f"""\
#define NNG_DECL
#define NNG_STATIC_LIB
#define NNG_DEPRECATED
{includes}
"""

    # Parse with headerkit libclang backend
    backend = get_backend("libclang")
    header = backend.parse(
        umbrella,
        "umbrella.h",
        include_dirs=[NNG_INCLUDE_DIR],
        project_prefixes=(NNG_INCLUDE_DIR,),
    )

    # Convert IR to CFFI cdef string
    cdef = header_to_cffi(header, exclude_patterns=EXCLUDE_PATTERNS)
    # Fix anonymous enum: nng.h defines `typedef enum { ... } nng_pipe_ev;`
    # without a tag name, so `enum nng_pipe_ev` is an incomplete type in C.
    cdef = re.sub(r"\benum\s+nng_pipe_ev\b", "nng_pipe_ev", cdef)

    # Extract additional #define constants from nng.h via regex
    # (libclang can miss macro values that involve expressions)
    nng_h_path = os.path.join(NNG_INCLUDE_DIR, "nng/nng.h")
    extra_defines = _extract_defines(nng_h_path)
    if extra_defines:
        cdef = cdef + "\n" + extra_defines

    # Write cdef to cache file and save hash
    with open(CDEF_CACHE_PATH, "w") as f:
        f.write(cdef)

    if _CACHE_AVAILABLE:
        try:
            save_hash(
                output_path=CDEF_CACHE_PATH,
                header_paths=header_paths,
                writer_name="cffi",
                extra_inputs=[build_script],
                writer=get_writer("cffi"),
            )
            print(f"CFFI cdef cache saved to {CDEF_CACHE_PATH}")
        except Exception as exc:
            print(f"Warning: failed to save cdef cache hash: {exc}")

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


# Generate cdef content and get the list of existing headers
cdef_content, _existing_headers = generate_cdef()

callbacks = """
    extern "Python" void _async_complete(void *);
    extern "Python" void _nng_pipe_cb(nng_pipe, nng_pipe_ev, void *);
"""

ffibuilder = FFI()

# Build set_source includes from the existing headers returned by generate_cdef()
_source_includes = "\n".join(f"        #include <{h}>" for h in _existing_headers)

ffibuilder.set_source(
    "pynng._nng",
    f"""
        #define NNG_DECL
        #define NNG_STATIC_LIB
{_source_includes}
    """,
    include_dirs=[NNG_INCLUDE_DIR],
)

ffibuilder.cdef(cdef_content + callbacks)

if __name__ == "__main__":
    ffibuilder.compile(verbose=True)
