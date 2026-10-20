"""Tests for the CFFI generation pipeline in build_pynng.py.

Validates that excluded patterns are properly filtered from the generated
FFI bindings.

These tests operate on the already-compiled _nng module to verify the end
result of the build pipeline.
"""

import os
import sys

import pytest

# Ensure the project root is on sys.path so that build_pynng.py is importable.
# This is necessary in cibuildwheel and other environments where pytest runs
# from a directory that doesn't include the project root.
_PROJECT_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

try:
    from pynng._nng import ffi, lib
    _has_compiled_nng = True
except ImportError:
    _has_compiled_nng = False
    ffi = None
    lib = None


# -- Tests against the compiled FFI module ------------------------------------


@pytest.mark.skipif(not _has_compiled_nng, reason="pynng._nng extension not yet compiled")
class TestFFIExcludePatterns:
    """Verify that EXCLUDE_PATTERNS properly filter sensitive TLS functions."""

    @pytest.mark.parametrize(
        "func_name",
        [
            "nng_tls_config_pass",
            "nng_tls_config_key",
        ],
    )
    def test_ffi_excludes_filtered_functions(self, func_name):
        assert not hasattr(lib, func_name)

    def test_ffi_retains_non_excluded_tls_functions(self):
        # nng_tls_config_alloc should NOT be excluded
        assert hasattr(lib, "nng_tls_config_alloc")


# -- Direct CFFI generation tests from NNG headers via HeaderKit --------------

_NNG_INCLUDE_DIR = os.environ.get("NNG_INCLUDE_DIR")
_has_nng_headers = _NNG_INCLUDE_DIR is not None and os.path.isdir(_NNG_INCLUDE_DIR)


@pytest.mark.skipif(not _has_nng_headers, reason="NNG_INCLUDE_DIR not set or not a directory")
class TestGenerateCDef:
    """Test CFFI declarations generation directly via HeaderKit and build_pynng."""

    def test_cdef_is_valid_cffi(self):
        """The generated cdef can be parsed by a fresh FFI without error."""
        import cffi
        from build_pynng import generate_cdef

        cdef, _headers = generate_cdef()
        test_ffi = cffi.FFI()
        test_ffi.cdef(cdef)

    def test_cdef_contains_core_types(self):
        from build_pynng import generate_cdef

        cdef, _headers = generate_cdef()
        for type_name in [
            "nng_socket",
            "nng_pipe",
            "nng_aio",
            "nng_ctx",
            "nng_msg",
            "nng_dialer",
            "nng_listener",
        ]:
            assert type_name in cdef, f"Missing type {type_name} in cdef"

    def test_cdef_contains_core_functions(self):
        from build_pynng import generate_cdef

        cdef, _headers = generate_cdef()
        for func in ["nng_send", "nng_recv", "nng_close", "nng_aio_alloc", "nng_ctx_open"]:
            assert func in cdef, f"Missing function {func} in cdef"

