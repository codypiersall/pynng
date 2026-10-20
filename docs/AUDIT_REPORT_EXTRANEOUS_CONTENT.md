# Comprehensive Documentation Audit: Extraneous & Internal Content Review

**Agent**: Maya Lin (`@pynng-docs`) — Documentation & Release Architect  
**Project**: `pynng`  
**Target Branch**: `v1-docs-overhaul`  
**Workspace**: `/Users/eek/Development/workspaces/pynng/task-3.1/pynng`  
**Audit Scope**: All files in `docs/` (`docs/api/`, guides, tutorials, legacy stubs)  
**Verification Target**: Sphinx HTML build (`sphinx-build -W -b html docs docs/_build/html`)

---

## Executive Summary

An exhaustive line-by-line empirical audit was conducted on the `v1-docs-overhaul` branch documentation. The current documentation is well-structured, modern, and compiles cleanly with **0 warnings** under `-W`. However, the audit identified several specific categories of extraneous internal plumbing, technical inaccuracies against the active codebase, orphaned legacy stubs, and omissions of newly landed v1 APIs.

---

## 1. Internal Plumbing in API Reference (`docs/api/options.rst`)

### Finding 1.1: Exposed Internal Descriptor Class
- **Location**: `docs/api/options.rst:21-22`
- **Content**:
  ```rst
  Option Descriptor
  -----------------

  .. autoclass:: pynng.nng._NNGOption
     :members:
  ```
- **Issue**: `_NNGOption` is an internal private implementation detail of `pynng.nng`. End-users never instantiate or interact with `_NNGOption` directly; they interact with public descriptors like `sock.recv_timeout`.
- **Severity**: Medium (Pollutes public API namespace with internal symbol).

### Finding 1.2: Exposed Internal CFFI Helper Functions
- **Location**: `docs/api/options.rst:24-38`
- **Content**:
  ```rst
  Internal Option Functions
  -------------------------

  These functions are used internally by the option descriptors. They are
  documented here for completeness but are not part of the public API.

  .. autofunction:: pynng.options._getopt_int
  .. autofunction:: pynng.options._setopt_int
  .. autofunction:: pynng.options._getopt_string
  .. autofunction:: pynng.options._getopt_bool
  .. autofunction:: pynng.options._getopt_ms
  .. autofunction:: pynng.options._setopt_ms
  .. autofunction:: pynng.options._getopt_size
  .. autofunction:: pynng.options._setopt_size
  .. autofunction:: pynng.options._getopt_sockaddr
  ```
- **Issue**: All 9 functions have leading underscores, are internal plumbing, and are explicitly acknowledged as "not part of the public API." Documenting internal CFFI wrappers in the user-facing API reference clutters documentation and invites unsupported coupling.
- **Remediation Recommendation**:
  Replace `_NNGOption` and all `_getopt_*` / `_setopt_*` functions with a comprehensive **Socket & Endpoint Options Reference Table** detailing public options (`recv_timeout`, `send_timeout`, `recv_max_size`, `recv_buffer_size`, `send_buffer_size`, `raw`, `tcp_nodelay`, `tcp_keepalive`, `resend_time`, `survey_time`, `polyamorous`, `tls_config`), their types, read/write permissions, and target objects (`Socket`, `Context`, `Dialer`, `Listener`, `Pipe`).

---

## 2. Technical Inaccuracies in API & Guides

### Finding 2.1: Inaccurate Context Support Claim
- **Locations**:
  - `docs/async.rst:291-292`:
    > *"Only :class:`~pynng.Req0` and :class:`~pynng.Rep0` support contexts. Other protocols raise an error when you call ``new_context()``."*
  - `docs/protocols.rst:160-161`:
    > *"Only Req0 and Rep0 support :class:`~pynng.Context`. Other protocols raise an error."*
- **Empirical Ground Truth**:
  NNG natively supports contexts (`nng_ctx_open`) on four protocols:
  1. `Req0`
  2. `Rep0`
  3. `Surveyor0`
  4. `Respondent0`
  Empirical test execution:
  ```python
  >>> import pynng
  >>> with pynng.Surveyor0() as s:
  ...     ctx = s.new_context()
  ...     print(ctx)
  <pynng.nng.Context object at 0x108d4c830>
  ```
  Calling `new_context()` on `Surveyor0` or `Respondent0` succeeds without error.
- **Remediation Recommendation**:
  Update both files to state:
  > *"Contexts are supported on :class:`~pynng.Req0`, :class:`~pynng.Rep0`, :class:`~pynng.Surveyor0`, and :class:`~pynng.Respondent0`. Calling ``new_context()`` on other protocols (e.g. Pub0, Sub0, Pair0, Push0, Pull0, Bus0) raises :class:`~pynng.NotSupported`."*

### Finding 2.2: Inaccurate Exception Hierarchy Claim & Exposed Internal Map
- **Location**: `docs/api/exceptions.rst:6-12`
- **Content**:
  > *"The root exception of the hierarchy is :class:`~pynng.NNGException`, which inherits from :class:`Exception`. All other exceptions defined in pynng inherit from ``NNGException``."*
  > `.. automodule:: pynng.exceptions :members: :undoc-members:`
- **Issues**:
  1. `MessageStateError` does **not** inherit from `NNGException`; it inherits directly from `Exception` (`pynng/exceptions.py:181`, confirmed in `docs/architecture.rst:145`).
  2. `automodule:: pynng.exceptions` with `:members:` causes Sphinx to dump the 30-entry internal dictionary `pynng.exceptions.EXCEPTION_MAP = {...}` directly into user-facing documentation.
  3. `check_err` is an internal CFFI function rather than a user-facing utility.
- **Remediation Recommendation**:
  1. Correct intro text: *"All NNG C error code exceptions inherit from :class:`~pynng.NNGException`. In addition, :class:`~pynng.MessageStateError` inherits directly from :class:`Exception` to signal invalid message buffer lifecycle states."*
  2. Use explicit `autoclass` directives or `:exclude-members: EXCEPTION_MAP, check_err` to prevent internal mapping tables from polluting the API documentation.

---

## 3. Orphaned / Legacy Stub Files

### Finding 3.1: Legacy `docs/core.rst`
- **Location**: `docs/core.rst:1-33`
- **Status**: Marked with `:orphan:`. Contains 33 lines of pointer notes to `api/sockets`, `api/messaging`, `api/networking`, `api/tls`, `api/exceptions`, and `async`.
- **References**: No active `.rst` file links to `docs/core.rst`.

### Finding 3.2: Legacy `docs/exceptions.rst`
- **Location**: `docs/exceptions.rst:1-13`
- **Status**: Marked with `:orphan:`. Contains 13 lines pointing to `api/exceptions`.
- **References**: No active `.rst` file links to `docs/exceptions.rst`.

### Tradeoff Assessment:
- **Keep Stubs**: Preserves HTTP 200 for legacy external bookmarks pointing to `pynng.readthedocs.io/en/latest/core.html` and `exceptions.html`.
- **Remove Stubs**: Removes clutter from source tree. If desired, URL redirection can be managed via ReadTheDocs dashboard or `sphinx-reredirects`.
- **Recommendation**: Retain the two stubs for v1.0.0 release backward URL compatibility, but clean up the internal labels (`_async-ergonomics`, `_available-protocols`) in `core.rst` to prevent cross-reference ambiguity.

---

## 4. Omissions of Newly Landed v1 APIs in Documentation

### Finding 4.1: Missing `Sub0` Topic Management Methods in User Guide
- **Location**: `docs/protocols.rst:76-86`
- **Omission**: Only documents `subscribe()` and `unsubscribe()`. Does not document:
  - `Sub0.subscriptions`: Returns a `frozenset` of active topic subscriptions.
  - `Sub0.subscribe_all(topics)`: Batch subscribes to an iterable of topics.
  - `Sub0.unsubscribe_all()`: Clears all active subscriptions atomically.
- **Remediation**: Add a section detailing `subscriptions`, `subscribe_all`, and `unsubscribe_all` with usage examples.

### Finding 4.2: Missing New Features in Migration Guide
- **Location**: `docs/migration.rst:148-160`
- **Omission**: "New Features Summary" lists async context managers, iteration, aclose, abstract sockets, and thread-safety, but omits:
  - High-level concurrent `Rep0Service` request/reply service.
  - Async pipe event streaming via `socket.pipe_events()`, `PipeEvent`, and `PipeEventStream`.
  - Batch subscription management (`subscribe_all`, `unsubscribe_all`, `subscriptions`).
- **Remediation**: Add bullets for `Rep0Service`, `pipe_events()`, and `Sub0` batch methods.

### Finding 4.3: Mention `Rep0Service` in `docs/async.rst`
- **Location**: `docs/async.rst:226-285`
- **Opportunity**: The "Concurrent Contexts" section describes manual context management with `rep.new_context()`. Adding a note linking to :class:`~pynng.Rep0Service` (`docs/api/service.rst`) gives users the high-level, idiomatic alternative for async server implementations.

---

## 5. Verification Status

- Sphinx strict compilation check:
  ```bash
  uv run --extra docs sphinx-build -W -b html docs docs/_build/html
  ```
  **Result**: Clean compilation, **0 warnings** with `-W`.
- Two-Key Gate (`vine gate`):
  **Result**: 100% Green (Mechanical clean merge-tree; Semantic 236 tests passed, 4 skipped).

---

## 6. Actionable Remediation Checklist

1. [ ] **Clean `docs/api/options.rst`**: Remove `_NNGOption` and `_getopt_*` / `_setopt_*`. Insert public option reference table.
2. [ ] **Fix Context Claims**: Correct `docs/async.rst:291` and `docs/protocols.rst:160` to include `Surveyor0` and `Respondent0`.
3. [ ] **Refine `docs/api/exceptions.rst`**: Clarify `MessageStateError` hierarchy; exclude `EXCEPTION_MAP` from doc dump.
4. [ ] **Enhance `docs/protocols.rst`**: Add `Sub0.subscriptions`, `subscribe_all`, and `unsubscribe_all` documentation.
5. [ ] **Update `docs/migration.rst`**: Include `Rep0Service`, `pipe_events()`, and `Sub0` batch methods in New Features Summary.
6. [ ] **Normalize Snippet Paths**: Ensure all snippet references across `docs/` use root-relative `/snippets/...` paths.
