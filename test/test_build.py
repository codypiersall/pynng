"""Tests for the CFFI generation pipeline in build_pynng.py.

Validates that the generated FFI bindings contain all expected nng types,
functions, and constants, and that excluded patterns are properly filtered.

These tests operate on the already-compiled _nng module to verify the end
result of the build pipeline. Where nng headers are available (via
NNG_INCLUDE_DIR or the build cache), they also test the build functions
directly.
"""

import glob
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


_skip_no_compiled_nng = pytest.mark.skipif(
    not _has_compiled_nng,
    reason="pynng._nng extension not yet compiled",
)


@_skip_no_compiled_nng
class TestFFICoreTypes:
    """Verify that the FFI knows about all core nng types."""

    @pytest.mark.parametrize(
        "type_name",
        [
            "nng_socket",
            "nng_pipe",
            "nng_aio",
            "nng_ctx",
            "nng_msg",
            "nng_dialer",
            "nng_listener",
        ],
    )
    def test_ffi_knows_core_types(self, type_name):
        # ffi.typeof raises FFIError if the type is unknown
        ffi.typeof(type_name)

    @pytest.mark.parametrize(
        "type_name",
        [
            "nng_socket *",
            "nng_pipe *",
            "nng_aio *",
            "nng_ctx *",
            "nng_msg *",
            "nng_dialer *",
            "nng_listener *",
        ],
    )
    def test_ffi_knows_pointer_types(self, type_name):
        ffi.typeof(type_name)


@_skip_no_compiled_nng
class TestFFICoreFunctions:
    """Verify that all expected protocol openers and core functions exist."""

    @pytest.mark.parametrize(
        "func_name",
        [
            "nng_pair0_open",
            "nng_pair1_open",
            "nng_req0_open",
            "nng_rep0_open",
            "nng_pub0_open",
            "nng_sub0_open",
            "nng_push0_open",
            "nng_pull0_open",
            "nng_bus0_open",
            "nng_surveyor0_open",
            "nng_respondent0_open",
        ],
    )
    def test_ffi_has_protocol_openers(self, func_name):
        assert hasattr(lib, func_name)

    @pytest.mark.parametrize(
        "func_name",
        [
            "nng_send",
            "nng_recv",
            "nng_close",
            "nng_aio_alloc",
            "nng_ctx_open",
            "nng_dial",
            "nng_listen",
            "nng_strerror",
            "nng_msg_alloc",
            "nng_msg_free",
        ],
    )
    def test_ffi_has_core_functions(self, func_name):
        assert hasattr(lib, func_name)


@_skip_no_compiled_nng
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


@_skip_no_compiled_nng
class TestFFIDefines:
    """Verify that #define constants extracted from nng.h are present."""

    @pytest.mark.parametrize(
        "define_name",
        [
            "NNG_FLAG_ALLOC",
            "NNG_FLAG_NONBLOCK",
            "NNG_MAXADDRLEN",
        ],
    )
    def test_ffi_has_flag_defines(self, define_name):
        assert hasattr(lib, define_name)

    def test_flag_alloc_is_integer(self):
        assert isinstance(lib.NNG_FLAG_ALLOC, int)

    def test_flag_nonblock_is_integer(self):
        assert isinstance(lib.NNG_FLAG_NONBLOCK, int)

    def test_maxaddrlen_is_positive(self):
        assert lib.NNG_MAXADDRLEN > 0


# -- Tests against build_pynng functions directly ----------------------------
# These require the nng include directory to be available (either via env var
# or auto-detected from the build cache).


def _candidate_build_roots() -> list[str]:
    roots = [_PROJECT_ROOT]
    dot_git = os.path.join(_PROJECT_ROOT, ".git")
    if os.path.isfile(dot_git):
        with open(dot_git, encoding="utf-8") as f:
            line = f.read().strip()
        if line.startswith("gitdir:"):
            gitdir = line.split(":", 1)[1].strip()
            if not os.path.isabs(gitdir):
                gitdir = os.path.normpath(os.path.join(_PROJECT_ROOT, gitdir))
            # .git/worktrees/<name> -> main repo root is 3 levels up
            main_root = os.path.normpath(os.path.join(gitdir, "..", "..", ".."))
            if os.path.isdir(main_root) and main_root not in roots:
                roots.append(main_root)
    return roots


_PY_TAG = f"cpython-{sys.version_info.major}{sys.version_info.minor}"
_NNG_INCLUDE_DIR = os.environ.get("NNG_INCLUDE_DIR")
if not _NNG_INCLUDE_DIR:
    _all_v1_candidates: list[str] = []
    for _root in _candidate_build_roots():
        _all_v1_candidates.extend(
            glob.glob(os.path.join(_root, "build", "*", "_deps", "nng-src", "include"))
        )
    if _all_v1_candidates:
        _all_v1_candidates.sort(key=lambda p: (_PY_TAG not in p, p))
        _NNG_INCLUDE_DIR = _all_v1_candidates[0]

_skip_no_headers = pytest.mark.skipif(
    _NNG_INCLUDE_DIR is None,
    reason="nng headers not available (set NNG_INCLUDE_DIR or build first)",
)


@_skip_no_headers
class TestHeaderkitWriters:
    """Test CffiWriter and PyiWriter integration in build_pynng against real nng headers."""

    @pytest.fixture(autouse=True)
    def _set_include_dir(self):
        old = os.environ.get("NNG_INCLUDE_DIR")
        os.environ["NNG_INCLUDE_DIR"] = _NNG_INCLUDE_DIR
        yield
        if old is None:
            os.environ.pop("NNG_INCLUDE_DIR", None)
        else:
            os.environ["NNG_INCLUDE_DIR"] = old

    def test_cdef_defines_are_deduplicated_and_exact(self):
        from build_pynng import generate_cdef

        cdef, _ = generate_cdef()
        define_lines = {
            line.split()[1]: line
            for line in cdef.splitlines()
            if line.startswith("#define ")
        }
        assert define_lines["NNG_FLAG_ALLOC"] == "#define NNG_FLAG_ALLOC 1"
        assert define_lines["NNG_FLAG_NONBLOCK"] == "#define NNG_FLAG_NONBLOCK 2"
        # Negative control: no duplicate #define ... lines appended at bottom
        alloc_lines = [line for line in cdef.splitlines() if "NNG_FLAG_ALLOC" in line]
        assert alloc_lines == ["#define NNG_FLAG_ALLOC 1"]

    def test_cdef_emits_extern_python_callbacks_and_aio_engine(self):
        from build_pynng import generate_cdef

        cdef, _ = generate_cdef()
        lines = {line.strip() for line in cdef.splitlines()}
        assert 'extern "Python" void _async_complete(void *);' in lines
        assert (
            'extern "Python" void _nng_pipe_cb(nng_pipe, nng_pipe_ev, void *);' in lines
        )
        assert "typedef struct pynng_mpsc_queue pynng_mpsc_queue_t;" in lines
        assert "pynng_mpsc_queue_t * pynng_mpsc_queue_new(int write_fd);" in lines
        # Negative control: no invented `enum nng_pipe_ev` tag references
        assert [line for line in lines if "enum nng_pipe_ev" in line] == []

    def test_generate_pyi_emits_cffi_mode_stub(self):
        import ast

        from build_pynng import generate_pyi

        pyi_text = generate_pyi()
        tree = ast.parse(pyi_text)
        top_level_ann = {
            node.target.id: ast.unparse(node.annotation)
            for node in tree.body
            if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name)
        }
        assert top_level_ann == {"ffi": "cffi.FFI", "lib": "_Lib"}
        lib_classes = [
            node
            for node in tree.body
            if isinstance(node, ast.ClassDef) and node.name == "_Lib"
        ]
        assert len(lib_classes) == 1
        lib_methods = {
            node.name
            for node in lib_classes[0].body
            if isinstance(node, ast.FunctionDef)
        }
        lib_attrs = {
            node.target.id
            for node in lib_classes[0].body
            if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name)
        }
        assert "nng_send" in lib_methods
        assert "nng_recv" in lib_methods
        assert "nng_tls_config_pass" not in lib_methods

        # All 13 aio_engine.h C functions and both extern "Python" callbacks must be on _Lib
        expected_aio_and_cb = {
            "_async_complete",
            "_nng_pipe_cb",
            "pynng_aio_entry_free",
            "pynng_aio_entry_is_idle",
            "pynng_aio_entry_new",
            "pynng_aio_entry_set_slot_id",
            "pynng_mpsc_drain_batch",
            "pynng_mpsc_queue_close",
            "pynng_mpsc_queue_free",
            "pynng_mpsc_queue_new",
            "pynng_native_aio_complete",
            "pynng_sync_recv_aio",
            "pynng_sync_recv_alloc",
            "pynng_sync_recv_free",
            "pynng_sync_recv_wait",
        }
        assert expected_aio_and_cb & lib_methods == expected_aio_and_cb

        # Negative controls: string macros and un-exported expression macros must not appear on _Lib
        assert "NNG_OPT_SOCKNAME" not in lib_attrs
        assert "NNG_RELEASE_SUFFIX" not in lib_attrs
        assert "NNG_MAXADDRSTRLEN" not in lib_attrs

        # If _nng is compiled, verify exact 1:1 member parity between _Lib and runtime dir(lib)
        if _has_compiled_nng:
            assert (lib_methods | lib_attrs) == set(dir(lib))

    def test_parse_nng_headers_memoization_avoids_duplicate_libclang_parses(
        self, monkeypatch
    ):
        import build_pynng

        build_pynng._PARSE_MEMO.clear()
        build_pynng._CDEF_MEMO.clear()
        parse_calls: list[str] = []
        real_get_backend = build_pynng.get_backend

        def tracking_get_backend(name: str):
            backend = real_get_backend(name)

            class _Proxy:
                def parse(self, *args, **kwargs):
                    parse_calls.append(name)
                    return backend.parse(*args, **kwargs)

            return _Proxy()

        monkeypatch.setattr(build_pynng, "get_backend", tracking_get_backend)
        cdef_out, _ = build_pynng.generate_cdef()
        pyi_out = build_pynng.generate_pyi()
        assert len(cdef_out) > 0
        assert len(pyi_out) > 0
        assert parse_calls == ["libclang"]

    def test_v2_cdef_emits_tagless_init_params_and_single_star_fn_ptrs(self):
        import ast

        from build_pynng import (
            EXCLUDE_PATTERNS_V2,
            NNG_V2_HEADERS,
            generate_cdef,
            generate_pyi,
        )

        v2_candidates: list[str] = []
        for root in _candidate_build_roots():
            v2_candidates.extend(
                glob.glob(os.path.join(root, "build", "*", "nng_v2_install", "include"))
            )
        if not v2_candidates:
            pytest.skip("nng v2 headers not found in build cache")
        v2_candidates.sort(key=lambda p: (_PY_TAG not in p, p))

        cdef, _ = generate_cdef(
            headers=NNG_V2_HEADERS,
            include_dir=v2_candidates[0],
            exclude_patterns=EXCLUDE_PATTERNS_V2,
        )
        lines = {line.strip() for line in cdef.splitlines()}
        assert "void * (*malloc_fn)(size_t);" in lines
        assert "void * (*calloc_fn)(size_t, size_t);" in lines
        assert "void (*free_fn)(void *, size_t);" in lines
        assert "nng_err nng_init(const nng_init_params * params);" in lines
        # Negative controls: no double-star function pointer fields or struct nng_init_params
        assert "void * (**malloc_fn)(size_t);" not in lines
        assert "typedef struct nng_init_params {" not in lines

        # Verify v2 .pyi stub matches runtime pynng._nng_v2.lib 1:1
        pyi_v2 = generate_pyi(
            headers=NNG_V2_HEADERS,
            include_dir=v2_candidates[0],
            exclude_patterns=EXCLUDE_PATTERNS_V2,
        )
        tree_v2 = ast.parse(pyi_v2)
        lib_cls_v2 = next(
            node
            for node in tree_v2.body
            if isinstance(node, ast.ClassDef) and node.name == "_Lib"
        )
        v2_pyi_members = {
            node.name for node in lib_cls_v2.body if isinstance(node, ast.FunctionDef)
        } | {
            node.target.id
            for node in lib_cls_v2.body
            if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name)
        }
        assert "NNG_OPT_SOCKNAME" not in v2_pyi_members
        assert "pynng_mpsc_queue_new" in v2_pyi_members
        assert "_async_complete" in v2_pyi_members
        try:
            import pynng._nng_v2 as nng_v2

            assert v2_pyi_members == set(dir(nng_v2.lib))
        except ImportError:
            pass


@_skip_no_headers
class TestGenerateCdef:
    """Test generate_cdef() from build_pynng against real nng headers."""

    @pytest.fixture(autouse=True)
    def _set_include_dir(self):
        old = os.environ.get("NNG_INCLUDE_DIR")
        os.environ["NNG_INCLUDE_DIR"] = _NNG_INCLUDE_DIR
        yield
        if old is None:
            os.environ.pop("NNG_INCLUDE_DIR", None)
        else:
            os.environ["NNG_INCLUDE_DIR"] = old

    def test_cdef_is_valid_cffi(self):
        """The generated cdef can be parsed by a fresh FFI without error."""
        from build_pynng import generate_cdef

        cdef, _headers = generate_cdef()
        test_ffi = __import__("cffi").FFI()
        # This will raise cffi.CDefError or cffi.FFIError if the cdef is bad
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

    def test_cdef_contains_protocol_openers(self):
        from build_pynng import generate_cdef

        cdef, _headers = generate_cdef()
        for func in [
            "nng_pair0_open",
            "nng_req0_open",
            "nng_rep0_open",
            "nng_pub0_open",
            "nng_sub0_open",
            "nng_push0_open",
            "nng_pull0_open",
            "nng_bus0_open",
            "nng_surveyor0_open",
            "nng_respondent0_open",
        ]:
            assert func in cdef, f"Missing function {func} in cdef"

    def test_cdef_excludes_filtered_patterns(self):
        from build_pynng import generate_cdef

        cdef, _headers = generate_cdef()
        assert "nng_tls_config_pass" not in cdef
        assert "nng_tls_config_key" not in cdef
        # But other TLS functions should be present
        assert "nng_tls_config_alloc" in cdef

    def test_cdef_contains_core_functions(self):
        from build_pynng import generate_cdef

        cdef, _headers = generate_cdef()
        for func in [
            "nng_send",
            "nng_recv",
            "nng_close",
            "nng_aio_alloc",
            "nng_ctx_open",
        ]:
            assert func in cdef, f"Missing function {func} in cdef"


@_skip_no_headers
class TestUmbrellaHeader:
    """Test that the umbrella header logic includes expected components."""

    @pytest.fixture(autouse=True)
    def _set_include_dir(self):
        old = os.environ.get("NNG_INCLUDE_DIR")
        os.environ["NNG_INCLUDE_DIR"] = _NNG_INCLUDE_DIR
        yield
        if old is None:
            os.environ.pop("NNG_INCLUDE_DIR", None)
        else:
            os.environ["NNG_INCLUDE_DIR"] = old

    def test_all_existing_headers_are_included(self):
        """Verify generate_cdef() output contains types/functions from all NNG headers."""
        from build_pynng import NNG_HEADERS, generate_cdef

        existing = [
            h for h in NNG_HEADERS if os.path.exists(os.path.join(_NNG_INCLUDE_DIR, h))
        ]
        assert len(existing) > 0, "No NNG headers found"

        # The actual test: verify that generate_cdef() produces output that
        # includes declarations from across the header set, not just nng.h.
        cdef, _headers = generate_cdef()

        # Core nng.h types
        assert "nng_socket" in cdef, "Missing nng_socket from nng/nng.h"

        # Protocol-specific openers prove that protocol headers were included
        protocol_markers = {
            "nng/protocol/pair0/pair.h": "nng_pair0_open",
            "nng/protocol/pair1/pair.h": "nng_pair1_open",
            "nng/protocol/bus0/bus.h": "nng_bus0_open",
            "nng/protocol/reqrep0/req.h": "nng_req0_open",
            "nng/protocol/reqrep0/rep.h": "nng_rep0_open",
            "nng/protocol/pubsub0/pub.h": "nng_pub0_open",
            "nng/protocol/pubsub0/sub.h": "nng_sub0_open",
            "nng/protocol/pipeline0/push.h": "nng_push0_open",
            "nng/protocol/pipeline0/pull.h": "nng_pull0_open",
            "nng/protocol/survey0/survey.h": "nng_surveyor0_open",
            "nng/protocol/survey0/respond.h": "nng_respondent0_open",
        }
        for header, marker in protocol_markers.items():
            if header in existing:
                assert marker in cdef, (
                    f"Header {header} exists but {marker} missing from cdef"
                )

        # TLS header inclusion (if present)
        if "nng/supplemental/tls/tls.h" in existing:
            assert "nng_tls_config_alloc" in cdef, (
                "TLS header exists but nng_tls_config_alloc missing from cdef"
            )


# -- v2 CFFI module tests -----------------------------------------------------


@pytest.mark.nng_v2
class TestV2FFICoreTypes:
    """Verify that the v2 FFI module knows about core NNG types."""

    @pytest.fixture(autouse=True)
    def _import_v2(self):
        v2 = pytest.importorskip("pynng._nng_v2")
        self.ffi = v2.ffi
        self.lib = v2.lib

    @pytest.mark.parametrize(
        "type_name",
        [
            "nng_socket",
            "nng_pipe",
            "nng_aio",
            "nng_ctx",
            "nng_msg",
            "nng_dialer",
            "nng_listener",
        ],
    )
    def test_v2_ffi_knows_core_types(self, type_name):
        self.ffi.typeof(type_name)


@pytest.mark.nng_v2
class TestV2FFICoreFunctions:
    """Verify that all expected v2-specific functions exist."""

    @pytest.fixture(autouse=True)
    def _import_v2(self):
        v2 = pytest.importorskip("pynng._nng_v2")
        self.lib = v2.lib

    @pytest.mark.parametrize(
        "func_name",
        [
            "nng_init",
            "nng_fini",
            "nng_socket_close",
            "nng_socket_proto_id",
            "nng_socket_proto_name",
            "nng_socket_peer_id",
            "nng_socket_peer_name",
            "nng_socket_raw",
            "nng_socket_recv",
            "nng_socket_send",
            "nng_socket_get_recv_poll_fd",
            "nng_socket_get_send_poll_fd",
            "nng_sub0_socket_subscribe",
            "nng_sub0_socket_unsubscribe",
        ],
    )
    def test_v2_has_specific_functions(self, func_name):
        assert hasattr(self.lib, func_name)

    @pytest.mark.parametrize(
        "func_name",
        [
            "nng_pair0_open",
            "nng_pair1_open",
            "nng_req0_open",
            "nng_rep0_open",
            "nng_pub0_open",
            "nng_sub0_open",
            "nng_push0_open",
            "nng_pull0_open",
            "nng_bus0_open",
            "nng_surveyor0_open",
            "nng_respondent0_open",
        ],
    )
    def test_v2_has_protocol_openers(self, func_name):
        assert hasattr(self.lib, func_name)

    @pytest.mark.parametrize(
        "func_name",
        [
            "nng_send",
            "nng_aio_alloc",
            "nng_ctx_open",
            "nng_dial",
            "nng_listen",
            "nng_strerror",
            "nng_msg_alloc",
            "nng_msg_free",
            "nng_recvmsg",
            "nng_sendmsg",
        ],
    )
    def test_v2_has_core_functions(self, func_name):
        assert hasattr(self.lib, func_name)


@pytest.mark.nng_v2
class TestV2Differences:
    """Verify expected differences between v1 and v2 CFFI modules."""

    @pytest.fixture(autouse=True)
    def _import_both(self):
        self.v1 = pytest.importorskip("pynng._nng")
        self.v2 = pytest.importorskip("pynng._nng_v2")

    def test_v2_has_nng_init(self):
        assert hasattr(self.v2.lib, "nng_init")

    def test_v1_lacks_nng_init(self):
        assert not hasattr(self.v1.lib, "nng_init")

    def test_v2_has_socket_close(self):
        assert hasattr(self.v2.lib, "nng_socket_close")

    def test_v1_has_nng_close(self):
        assert hasattr(self.v1.lib, "nng_close")

    def test_v1_has_flag_alloc(self):
        assert hasattr(self.v1.lib, "NNG_FLAG_ALLOC")

    def test_v2_has_flag_nonblock(self):
        assert hasattr(self.v2.lib, "NNG_FLAG_NONBLOCK")


class TestPyPyHeaderkitCompat:
    """Verify headerkit integration, PEP 508 requirements, CMake rules, and public __all__ exports."""

    @pytest.fixture(autouse=True)
    def _require_headerkit(self):
        pytest.importorskip("headerkit")

    def test_headerkit_clang_imports_cleanly_without_custom_meta_path_finder(self):
        import headerkit._clang

        import build_pynng

        assert headerkit._clang is not None
        assert not hasattr(build_pynng, "_PyPyHeaderkitClangFinder")
        assert not hasattr(build_pynng, "_transform_headerkit_clang_source")
        assert not hasattr(build_pynng, "_extract_defines")
        finder_names = {type(finder).__name__ for finder in sys.meta_path}
        assert "_PyPyHeaderkitClangFinder" not in finder_names

    def test_pyproject_requirements_are_valid_pep508(self):
        """Verify all pyproject.toml requirement strings parse cleanly under PEP 508."""
        import tomllib
        from packaging.requirements import Requirement

        pyproject_path = os.path.join(_PROJECT_ROOT, "pyproject.toml")
        with open(pyproject_path, "rb") as f:
            data = tomllib.load(f)

        all_reqs = (
            list(data["project"]["dependencies"])
            + list(data["project"]["optional-dependencies"]["dev"])
            + list(data["project"]["optional-dependencies"]["docs"])
            + list(data["build-system"]["requires"])
        )
        parsed = {req_str: Requirement(req_str).name for req_str in all_reqs}
        assert parsed["headerkit~=0.50.0 ; python_version >= '3.11'"] == "headerkit"
        assert "uv" not in data.get("tool", {}) or "sources" not in data["tool"]["uv"]

    def test_require_headerkit_raises_runtime_error_when_unavailable(self, monkeypatch):
        """Negative control: calling build functions without headerkit raises a clear RuntimeError."""
        import build_pynng

        monkeypatch.setattr(build_pynng, "_HAS_HEADERKIT", False)
        with pytest.raises(
            RuntimeError, match="headerkit \\(requires Python >= 3\\.11\\)"
        ):
            build_pynng._require_headerkit()

    def test_cmake_pyi_install_rules_exist(self):
        """Verify CMakeLists.txt registers .pyi BYPRODUCTS and installs .pyi stubs."""
        cmake_path = os.path.join(_PROJECT_ROOT, "CMakeLists.txt")
        with open(cmake_path, encoding="utf-8") as f:
            cmake_lines = {line.strip() for line in f.read().splitlines()}

        assert "BYPRODUCTS ${CMAKE_CURRENT_SOURCE_DIR}/pynng/_nng.pyi" in cmake_lines
        assert "BYPRODUCTS ${CMAKE_CURRENT_SOURCE_DIR}/pynng/_nng_v2.pyi" in cmake_lines
        assert 'PATTERN "*.pyi"' in cmake_lines
        assert 'PATTERN "py.typed"' in cmake_lines

    def test_py_typed_marker_exists(self):
        """Verify PEP 561 py.typed marker exists in the pynng package directory."""
        py_typed_path = os.path.join(_PROJECT_ROOT, "pynng", "py.typed")
        assert os.path.isfile(py_typed_path)

    def test_all_python_modules_have_pep484_type_annotations(self):
        """Verify every function and method across all pynng Python modules has PEP 484 type annotations."""
        import ast
        import glob

        pynng_dir = os.path.join(_PROJECT_ROOT, "pynng")
        py_files = [
            path
            for path in sorted(
                glob.glob(os.path.join(pynng_dir, "**", "*.py"), recursive=True)
            )
            if not path.endswith("_version.py")
        ]
        assert len(py_files) == 14

        untyped: list[str] = []
        for path in py_files:
            rel_path = os.path.relpath(path, _PROJECT_ROOT)
            with open(path, encoding="utf-8") as f:
                tree = ast.parse(f.read(), filename=rel_path)
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if node.returns is None:
                        untyped.append(
                            f"{rel_path}:{node.lineno} {node.name} missing return annotation"
                        )
                    args = node.args.posonlyargs + node.args.args + node.args.kwonlyargs
                    if node.args.vararg is not None:
                        args.append(node.args.vararg)
                    if node.args.kwarg is not None:
                        args.append(node.args.kwarg)
                    for idx, arg in enumerate(args):
                        if idx == 0 and arg.arg in ("self", "cls"):
                            continue
                        if arg.annotation is None:
                            untyped.append(
                                f"{rel_path}:{node.lineno} {node.name}({arg.arg}) missing parameter annotation"
                            )

        assert untyped == []

    def test_zero_any_annotations_across_pynng(self):
        """Verify zero Any imports, zero | Any unions, and zero Any annotations across pynng."""
        import ast
        import glob

        pynng_dir = os.path.join(_PROJECT_ROOT, "pynng")
        py_files = [
            path
            for path in sorted(
                glob.glob(os.path.join(pynng_dir, "**", "*.py"), recursive=True)
            )
            if not path.endswith("_version.py")
        ]
        assert len(py_files) == 14

        any_violations: list[str] = []
        for path in py_files:
            rel_path = os.path.relpath(path, _PROJECT_ROOT)
            with open(path, encoding="utf-8") as f:
                tree = ast.parse(f.read(), filename=rel_path)
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom):
                    for alias in node.names:
                        if alias.name == "Any":
                            any_violations.append(
                                f"{rel_path}:{node.lineno} imports Any"
                            )
                elif isinstance(node, ast.Name) and node.id == "Any":
                    any_violations.append(f"{rel_path}:{node.lineno} references Any")

        assert any_violations == []

    def test_protocol_sockets_have_explicit_init_parameters_without_kwargs(self):
        """Verify Socket and all 22 protocol classes in v1 and v2 have explicit __init__ parameters and no **kwargs."""
        import ast

        protocol_classes = (
            "Socket",
            "Bus0",
            "Pair0",
            "Pair1",
            "Push0",
            "Pull0",
            "Pub0",
            "Sub0",
            "Req0",
            "Rep0",
            "Surveyor0",
            "Respondent0",
            "RawBus0",
            "RawPair0",
            "RawPair1",
            "RawPush0",
            "RawPull0",
            "RawPub0",
            "RawSub0",
            "RawReq0",
            "RawRep0",
            "RawSurveyor0",
            "RawRespondent0",
        )
        base_kwargs = {
            "dial",
            "listen",
            "recv_timeout",
            "send_timeout",
            "recv_buffer_size",
            "send_buffer_size",
            "recv_max_size",
            "reconnect_time_min",
            "reconnect_time_max",
            "opener",
            "raw",
            "block_on_dial",
            "async_backend",
            "tls_config",
        }
        extra_kwargs: dict[str, set[str]] = {
            "Pair1": {"polyamorous"},
            "RawPair1": {"polyamorous"},
            "Sub0": {"topics"},
            "RawSub0": {"topics"},
            "Req0": {"resend_time"},
            "RawReq0": {"resend_time"},
            "Surveyor0": {"survey_time"},
            "RawSurveyor0": {"survey_time"},
        }

        for rel_path, has_name in (
            ("pynng/nng.py", True),
            ("pynng/v2/nng.py", False),
        ):
            full_path = os.path.join(_PROJECT_ROOT, rel_path)
            with open(full_path, encoding="utf-8") as f:
                tree = ast.parse(f.read(), filename=rel_path)

            class_defs = {
                node.name: node for node in tree.body if isinstance(node, ast.ClassDef)
            }
            for cls_name in protocol_classes:
                assert cls_name in class_defs, f"{cls_name} missing in {rel_path}"
                cls_node = class_defs[cls_name]
                init_nodes = [
                    n
                    for n in cls_node.body
                    if isinstance(n, ast.FunctionDef) and n.name == "__init__"
                ]
                assert len(init_nodes) == 1, (
                    f"{rel_path}:{cls_name} must define explicit __init__"
                )
                init_node = init_nodes[0]
                assert init_node.args.kwarg is None, (
                    f"{rel_path}:{cls_name}.__init__ must not use **kwargs"
                )
                kwonly_names = {arg.arg for arg in init_node.args.kwonlyargs}
                expected = set(base_kwargs) | extra_kwargs.get(cls_name, set())
                if has_name:
                    expected.add("name")
                assert kwonly_names == expected, (
                    f"{rel_path}:{cls_name}.__init__ kwargs mismatch: "
                    f"{kwonly_names} != {expected}"
                )

    @_skip_no_headers
    def test_build_pynng_executes_without_dunder_file_in_globals(self, monkeypatch):
        """Verify build_pynng.py runs cleanly via exec() when __file__ is absent (as in cffi_buildtool)."""
        assert _NNG_INCLUDE_DIR is not None
        monkeypatch.setenv("NNG_INCLUDE_DIR", _NNG_INCLUDE_DIR)
        monkeypatch.chdir(_PROJECT_ROOT)
        build_script = os.path.join(_PROJECT_ROOT, "build_pynng.py")
        pyi_path = os.path.join(_PROJECT_ROOT, "pynng", "_nng.pyi")
        prev_pyi: bytes | None = None
        if os.path.exists(pyi_path):
            with open(pyi_path, "rb") as f:
                prev_pyi = f.read()

        with open(build_script, encoding="utf-8") as f:
            source = f.read()

        globs: dict[str, object] = {"__name__": "gen-cffi-src"}
        compiled = compile(source, build_script, "exec")
        try:
            exec(compiled, globs, globs)
        finally:
            if prev_pyi is not None:
                with open(pyi_path, "wb") as f:
                    f.write(prev_pyi)
            elif os.path.exists(pyi_path):
                os.remove(pyi_path)

        assert "__file__" not in globs
        assert "ffibuilder" in globs
        assert globs["ffibuilder"] is not None

    @_skip_no_compiled_nng
    def test_public_modules_define_explicit_all_exports(self):
        """Verify pynng, pynng.nng, pynng.v2, and pynng.v2.nng define explicit __all__ exports."""
        import pynng
        import pynng.nng

        for mod in (pynng, pynng.nng):
            assert hasattr(mod, "__all__")
            assert isinstance(mod.__all__, list)
            assert len(mod.__all__) > 0
            missing = [name for name in mod.__all__ if not hasattr(mod, name)]
            assert missing == [], (
                f"Missing attributes in {mod.__name__}.__all__: {missing}"
            )

        for required in (
            "__version__",
            "lib",
            "ffi",
            "Socket",
            "Pair0",
            "Req0",
            "Rep0",
            "PipeEvent",
            "PipeEventStream",
            "Request",
            "nng_fini",
            "nng_fini_at_exit",
        ):
            assert required in pynng.__all__

        try:
            import pynng.v2
            import pynng.v2.nng
        except ImportError:
            return

        for mod in (pynng.v2, pynng.v2.nng):
            assert hasattr(mod, "__all__")
            assert isinstance(mod.__all__, list)
            assert len(mod.__all__) > 0
            missing = [name for name in mod.__all__ if not hasattr(mod, name)]
            assert missing == [], (
                f"Missing attributes in {mod.__name__}.__all__: {missing}"
            )

        for required in (
            "__version__",
            "lib",
            "ffi",
            "Socket",
            "Pair0",
            "Req0",
            "Rep0",
            "PipeEvent",
            "PipeEventStream",
            "Request",
            "nng_fini",
            "nng_fini_at_exit",
        ):
            assert required in pynng.v2.__all__
        assert "nng_fini" in pynng.v2.nng.__all__
        assert "nng_fini_at_exit" in pynng.v2.nng.__all__

    def test_committed_pyi_stubs_exist_and_not_gitignored(self, monkeypatch, tmp_path):
        """Verify pynng/_nng.pyi and pynng/_nng_v2.pyi are tracked on disk and guarded against partial-TLS overwrites."""
        import ast

        import build_pynng

        gitignore_path = os.path.join(_PROJECT_ROOT, ".gitignore")
        with open(gitignore_path, encoding="utf-8") as f:
            gitignore_lines = {
                line.strip()
                for line in f.read().splitlines()
                if line.strip() and not line.strip().startswith("#")
            }
        assert "pynng/_nng.pyi" not in gitignore_lines
        assert "pynng/_nng_v2.pyi" not in gitignore_lines

        v1_pyi_path = os.path.join(_PROJECT_ROOT, "pynng", "_nng.pyi")
        v2_pyi_path = os.path.join(_PROJECT_ROOT, "pynng", "_nng_v2.pyi")
        assert os.path.isfile(v1_pyi_path)
        assert os.path.isfile(v2_pyi_path)

        with open(v1_pyi_path, encoding="utf-8") as f:
            v1_pyi_text = f.read()
        with open(v2_pyi_path, encoding="utf-8") as f:
            v2_pyi_text = f.read()

        v1_tree = ast.parse(v1_pyi_text, filename="pynng/_nng.pyi")
        v2_tree = ast.parse(v2_pyi_text, filename="pynng/_nng_v2.pyi")

        def _extract_lib_members(tree: ast.Module) -> set[str]:
            lib_cls = next(
                node
                for node in tree.body
                if isinstance(node, ast.ClassDef) and node.name == "_Lib"
            )
            return {
                node.name
                for node in lib_cls.body
                if isinstance(node, ast.FunctionDef)
            } | {
                node.target.id
                for node in lib_cls.body
                if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name)
            }

        v1_members = _extract_lib_members(v1_tree)
        v2_members = _extract_lib_members(v2_tree)
        assert "NNG_TLS_AUTH_MODE_NONE" in v1_members
        assert "nng_tls_config_psk" in v1_members
        assert "NNG_TLS_AUTH_MODE_NONE" in v2_members
        assert "NNG_TLS_1_2" in v2_members

        if _has_compiled_nng:
            assert v1_members == set(dir(lib))
        try:
            import pynng._nng_v2 as nng_v2

            assert v2_members == set(dir(nng_v2.lib))
        except ImportError:
            pass

        if _NNG_INCLUDE_DIR is not None:
            pyi_no_tls = build_pynng.generate_pyi(
                include_dir=_NNG_INCLUDE_DIR,
                tls_enabled=False,
            )
            no_tls_members = _extract_lib_members(ast.parse(pyi_no_tls))
            assert "nng_tls_config_psk" not in no_tls_members

            # Verify partial build (tls_enabled=False) does not overwrite an existing .pyi stub
            fake_pkg_dir = tmp_path / "pynng"
            fake_pkg_dir.mkdir()
            fake_stub = fake_pkg_dir / "_nng.pyi"
            sentinel = "# existing full stub\n"
            fake_stub.write_text(sentinel, encoding="utf-8")
            monkeypatch.setattr(build_pynng, "_SCRIPT_DIR", str(tmp_path))
            build_pynng._build_ffi(
                module_name="pynng._nng",
                include_dir=_NNG_INCLUDE_DIR,
                tls_enabled=False,
            )
            assert fake_stub.read_text(encoding="utf-8") == sentinel

    def test_mypy_strict_and_pyright_pass_with_zero_issues(self, tmp_path):
        """Verify mypy --strict and pyright pass with zero errors on pynng and consumer code."""
        import subprocess
        import textwrap

        pytest.importorskip("mypy")
        pytest.importorskip("pyright")

        mypy_res = subprocess.run(
            [sys.executable, "-m", "mypy", "--strict", "pynng"],
            cwd=_PROJECT_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        assert mypy_res.returncode == 0, (
            f"mypy --strict failed:\n{mypy_res.stdout}\n{mypy_res.stderr}"
        )
        assert "Success: no issues found" in mypy_res.stdout

        pyright_res = subprocess.run(
            [
                sys.executable,
                "-m",
                "pyright",
                "--pythonpath",
                sys.executable,
                "pynng",
            ],
            cwd=_PROJECT_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        assert pyright_res.returncode == 0, (
            f"pyright failed:\n{pyright_res.stdout}\n{pyright_res.stderr}"
        )
        assert "0 errors, 0 warnings, 0 informations" in pyright_res.stdout

        valid_consumer = tmp_path / "valid_consumer.py"
        valid_consumer.write_text(
            textwrap.dedent(
                """\
                from __future__ import annotations
                import pynng
                import pynng.v2 as v2
                from pynng._base import MsOption, PointerOption, ReadOnlyIntOption, SockAddrOption

                desc_proto: ReadOnlyIntOption = pynng.Socket.protocol
                desc_timeout: MsOption = pynng.Socket.recv_timeout
                desc_tls: PointerOption = pynng.Socket.tls_config
                desc_addr: SockAddrOption = pynng.Dialer.local_address

                async def exercise_types(req: pynng.Request) -> None:
                    with pynng.Pair0(listen="inproc://t1", name=b"bname") as s1:
                        proto: int = s1.protocol
                        s1.name = b"updated"
                        s1.name = "updated-str"
                        with s1.listen("inproc://t2") as listener:
                            lsock: pynng.Socket = listener.socket
                            _ = lsock.protocol
                        with s1.dial("inproc://t1") as dialer:
                            dsock: pynng.Socket = dialer.socket
                            _ = dsock.protocol
                        msg = pynng.Message(b"hello")
                        msg2: pynng.Message = msg.copy()
                        msg3: pynng.Message = msg.dup()
                        _ = (proto, msg2, msg3)

                    with v2.Pair0(listen="inproc://v2_t1") as vs1:
                        with vs1.listen("inproc://v2_t2") as vlistener:
                            vlsock: v2.Socket = vlistener.socket
                            _ = vlsock.protocol
                        vmsg = v2.Message(b"hello")
                        vmsg2: v2.Message = vmsg.copy()
                        _ = vmsg2

                    async with v2.Rep0Service("inproc://v2_svc") as svc:
                        svc_typed: v2.Rep0Service = svc
                        _ = svc_typed

                    await req.reply(bytearray(b"ok"))
                    await req.reply(memoryview(b"ok"))
                    _ = v2.nng.nng_fini
                    _ = v2.nng.nng_fini_at_exit
                """
            ),
            encoding="utf-8",
        )

        env = os.environ.copy()
        env["MYPYPATH"] = _PROJECT_ROOT
        env["PYTHONPATH"] = _PROJECT_ROOT

        valid_mypy = subprocess.run(
            [sys.executable, "-m", "mypy", "--strict", str(valid_consumer)],
            cwd=_PROJECT_ROOT,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        assert valid_mypy.returncode == 0, (
            f"valid_consumer mypy failed:\n{valid_mypy.stdout}\n{valid_mypy.stderr}"
        )

        invalid_consumer = tmp_path / "invalid_consumer.py"
        invalid_consumer.write_text(
            textwrap.dedent(
                """\
                import pynng
                import pynng.v2 as v2

                def bad(s: pynng.Pair0, d: pynng.Dialer, vd: v2.Dialer) -> None:
                    s.protocol = 1
                    s.raw = True
                    d.url = "tcp://127.0.0.1:80"
                    _ = s.tls_config
                    _ = vd.tcp_nodelay
                """
            ),
            encoding="utf-8",
        )
        invalid_mypy = subprocess.run(
            [sys.executable, "-m", "mypy", "--strict", str(invalid_consumer)],
            cwd=_PROJECT_ROOT,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        assert invalid_mypy.returncode != 0
        assert invalid_mypy.stdout.count("error:") == 5

    @_skip_no_compiled_nng
    def test_option_descriptors_and_v1_v2_runtime_contracts(self):
        """Verify runtime option descriptor behavior, sync endpoint context managers, and v1/v2 separation."""
        import pynng
        from pynng._base import (
            MsOption,
            PointerOption,
            ReadOnlyBooleanOption,
            ReadOnlyIntOption,
            ReadOnlyStringOption,
            SockAddrOption,
        )

        # Class-level descriptor access returns the descriptor object itself
        assert isinstance(pynng.Socket.recv_timeout, MsOption)
        assert isinstance(pynng.Socket.raw, ReadOnlyBooleanOption)
        assert isinstance(pynng.Socket.protocol, ReadOnlyIntOption)
        assert isinstance(pynng.Socket.protocol_name, ReadOnlyStringOption)
        assert isinstance(pynng.Socket.tls_config, PointerOption)
        assert isinstance(pynng.Dialer.local_address, SockAddrOption)
        assert isinstance(pynng.Dialer.url, ReadOnlyStringOption)
        assert isinstance(pynng.Pipe.local_address, SockAddrOption)

        # Misleading local_address removed from Socket docstring
        assert pynng.Socket.__doc__ is not None
        assert "local_address" not in pynng.Socket.__doc__

        # Redundant import builtins removed from pynng/_base.py
        base_path = os.path.join(_PROJECT_ROOT, "pynng", "_base.py")
        with open(base_path, encoding="utf-8") as f:
            base_source = f.read()
        assert "import builtins" not in base_source

        with pynng.Pair0() as sock:
            sock.name = b"bytes-sock-name"
            assert sock.name == "bytes-sock-name"

            # Read-only options raise TypeError on write
            with pytest.raises(TypeError, match="readonly"):
                sock.protocol = 1  # type: ignore[misc]
            with pytest.raises(TypeError, match="readonly"):
                sock.raw = True  # type: ignore[misc]
            with pytest.raises(TypeError, match="readonly"):
                sock.recv_fd = 1  # type: ignore[misc]

            # Write-only PointerOption raises TypeError on instance read
            with pytest.raises(TypeError, match="write-only"):
                _ = sock.tls_config  # type: ignore[arg-type]

            # Synchronous context manager on Listener and Dialer
            with sock.listen("inproc://sync-cm-test") as listener:
                assert listener.id > 0
                assert listener.socket is sock
                with pytest.raises(TypeError, match="readonly"):
                    listener.url = "inproc://other"  # type: ignore[misc]
                with pynng.Pair0() as client:
                    with client.dial("inproc://sync-cm-test") as dialer:
                        assert dialer.id > 0
                        assert dialer.socket is client
                    assert client.dialers == ()
            assert sock.listeners == ()

            msg = pynng.Message(b"abc")
            dup_msg = msg.copy()
            assert isinstance(dup_msg, pynng.Message)
            assert dup_msg.bytes == b"abc"

        try:
            import pynng.v2 as v2
            import pynng.v2.nng as v2_nng
        except ImportError:
            return

        # Zero # type: ignore[override] comments in pynng/v2/nng.py
        v2_nng_path = os.path.join(_PROJECT_ROOT, "pynng", "v2", "nng.py")
        with open(v2_nng_path, encoding="utf-8") as f:
            v2_nng_source = f.read()
        assert "type: ignore[override]" not in v2_nng_source

        # v1-only option descriptors are not inherited by v2.Dialer, v2.Listener, or v2.Pipe
        for v1_only_attr in (
            "tcp_nodelay",
            "tcp_keepalive",
            "reconnect_time_min",
            "reconnect_time_max",
            "recv_max_size",
            "peer",
            "peer_name",
        ):
            assert not hasattr(v2.Dialer, v1_only_attr)
            assert not hasattr(v2.Listener, v1_only_attr)

        for v1_only_pipe_attr in (
            "url",
            "protocol",
            "protocol_name",
            "peer",
            "peer_name",
        ):
            assert not hasattr(v2.Pipe, v1_only_pipe_attr)

        # v2.nng_fini_at_exit forwards to v2.nng.nng_fini_at_exit
        orig_flag = v2_nng.nng_fini_at_exit
        try:
            v2.nng_fini_at_exit = True
            assert v2_nng.nng_fini_at_exit is True
            v2_nng.nng_fini_at_exit = False
            assert v2.nng_fini_at_exit is False
        finally:
            v2_nng.nng_fini_at_exit = orig_flag


class TestAioEngineHeader:
    """Verify that the standalone pure C AIO completion engine header is valid."""

    def test_aio_engine_header_exists_and_contains_declarations(self):
        import build_pynng

        assert not hasattr(build_pynng, "_AIO_ENGINE_CDEF")
        header_path = build_pynng._AIO_ENGINE_H
        assert os.path.isfile(header_path), f"Header not found: {header_path}"

        with open(header_path, encoding="utf-8") as f:
            content = f.read()

        # Invariants: Include guards, CFFI cdef guard, 3 opaque typedefs, and 13 C API functions
        assert "#ifndef PYNNG_AIO_ENGINE_H" in content
        assert "#define PYNNG_AIO_ENGINE_H" in content
        assert "#ifdef PYNNG_CFFI_CDEF" in content
        assert "typedef struct pynng_aio_entry pynng_aio_entry_t;" in content
        assert "typedef struct pynng_mpsc_queue pynng_mpsc_queue_t;" in content
        assert "typedef struct pynng_sync_recv pynng_sync_recv_t;" in content

        required_symbols = [
            "pynng_mpsc_queue_new",
            "pynng_mpsc_queue_close",
            "pynng_mpsc_queue_free",
            "pynng_aio_entry_new",
            "pynng_aio_entry_set_slot_id",
            "pynng_aio_entry_is_idle",
            "pynng_aio_entry_free",
            "pynng_native_aio_complete",
            "pynng_mpsc_drain_batch",
            "pynng_sync_recv_alloc",
            "pynng_sync_recv_aio",
            "pynng_sync_recv_wait",
            "pynng_sync_recv_free",
        ]
        for sym in required_symbols:
            assert sym in content, f"Symbol {sym} missing from aio_engine.h"

    @_skip_no_compiled_nng
    def test_compiled_nng_has_aio_engine_symbols(self):
        """Verify compiled _nng extension exports all 13 AIO engine functions."""
        required_symbols = [
            "pynng_mpsc_queue_new",
            "pynng_mpsc_queue_close",
            "pynng_mpsc_queue_free",
            "pynng_aio_entry_new",
            "pynng_aio_entry_set_slot_id",
            "pynng_aio_entry_is_idle",
            "pynng_aio_entry_free",
            "pynng_native_aio_complete",
            "pynng_mpsc_drain_batch",
            "pynng_sync_recv_alloc",
            "pynng_sync_recv_aio",
            "pynng_sync_recv_wait",
            "pynng_sync_recv_free",
        ]
        for sym in required_symbols:
            assert hasattr(lib, sym), f"_nng.lib missing AIO symbol {sym}"
            assert callable(getattr(lib, sym)), f"_nng.lib.{sym} is not callable"
