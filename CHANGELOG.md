# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Non-blocking convenience methods on both `Socket` and `Context`: `recv_nowait()`, `send_nowait()`, `recv_msg_nowait()`, `send_msg_nowait()`, and `recv_into_nowait()`
- High-performance wait-free C11 MPSC intrusive queue engine and helper pooling for zero-GIL async I/O completions and up to 2x throughput speedups
- Hardened performance benchmark suite with GC-pause isolation, best-of-N multi-trial execution, and TCP nodelay optimization for reproducible CI measurement
- Dual-version coexistence with nng v2.0.0 GA under the `pynng.v2` namespace (`pynng.v2.Bus0`, `pynng.v2.Req0`, `pynng.v2.Rep0`, `pynng.v2.Pair0`, `pynng.v2.Pair1`, `pynng.v2.Pub0`, `pynng.v2.Sub0`, `pynng.v2.Push0`, `pynng.v2.Pull0`, `pynng.v2.Surveyor0`, `pynng.v2.Respondent0`)
- Pluggable TLS engine support via CMake `NNG_TLS_ENGINE` supporting `mbedTLS`, `wolfSSL`, `OpenSSL`, and `none`
- Raw socket wrapper classes (`RawBus0`, `RawPair0`, `RawPair1`, `RawReq0`, `RawRep0`, `RawPub0`, `RawSub0`, `RawPush0`, `RawPull0`, `RawSurveyor0`, `RawRespondent0`) for broker and proxy topologies
- `pynng.device()` and async `pynng.adevice()` forwarding proxies for kernel-level bridging
- Zero-copy Python buffer protocol support (`Socket.recv_into`, `Socket.arecv_into`, memoryview/bytearray send) across both v1 and v2
- Message header manipulation and inspection (`Message.header`, `msg.header_insert()`, `msg.header_append()`, `msg.header_trim()`, `msg.header_chop()`)
- Runtime statistics extraction via `pynng.stats()` and `socket.get_stat()`
- Comprehensive Sphinx documentation overhaul with dedicated per-class API references, interactive guides, and architecture documentation
- `Surveyor0.asurvey()` method for ergonomic async survey/collect pattern (sends survey, collects all responses until timeout, returns list)
- `Rep0Service` high-level async service class for concurrent request/reply handling with multiple context workers
- `Request` class with `.data` and `.reply()` for ergonomic request processing within `Rep0Service`
- `async with` context manager support for sockets (`async with pynng.Pair0() as sock:`)
- `async for` iteration over received messages (`async for msg in sock:`)
- `aclose()` method for explicit async socket cleanup
- `async with` context manager support for `Dialer` and `Listener`
- `aclose()` method for `Dialer` and `Listener`
- `recv_timeout` and `send_timeout` option descriptors on `Context` for per-context timeout control
- `Sub0.subscriptions` property to inspect current subscriptions as a frozenset
- `Sub0.subscribe_all(topics)` for batch subscription to multiple topics
- `Sub0.unsubscribe_all()` to clear all current subscriptions
- Local subscription tracking in `Sub0` (nng has no API to query subscriptions)
- `socket.pipe_events()` returns an async iterator of `PipeEvent` objects for consuming pipe connect/disconnect events (`async for event in socket.pipe_events()`)

- Support Python 3.15 in package classifiers and CI smoketest matrix
- Support PyPy 3.11 in CI smoketest matrix, `cibuildwheel` release builds, and PyPI implementation classifiers
- `pynng.nng_fini()` function and `nng_fini_at_exit` setting for explicit runtime finalization control

### Changed
- Upgrade bundled v1 NNG from v1.11 to v1.12.5, incorporating upstream fixes for large IOV scatter/gather transfers, mbedTLS CVE-2025-27809, and AIO task abort race conditions while removing obsolete patch files
- Extract native C completion queue engine from `build_pynng.py` into standalone `src/aio_engine.h` header for improved maintainability, modularity, and compiler diagnostics
- Enable `__slots__` on hot-path `Message`, `Request`, `Stat`, and `SockAddr` model classes to eliminate per-instance `__dict__` allocation overhead
- Switch cibuildwheel to uv build frontend, eliminating virtualenv.pyz downloads
- Migrate build system from setuptools/CMake to scikit-build-core with headerkit for C header generation
- Replace handwritten CFFI bindings with auto-generated bindings from nng headers via headerkit
- Add CI concurrency groups to cancel stale workflow runs
- Scope cibuildwheel tests to exclude build-system tests (run in smoketest instead)
- Python 3.10 EOL deprecation advisory in documentation and README
- Modernize GitHub Actions workflows to Node 24-compatible actions
- `post_pipe_remove` callbacks for a pipe now wait until the running `pre_pipe_connect` and `post_pipe_connect` callbacks for that pipe return, so a remove callback no longer runs at the same time as a connect callback for the same pipe
- A synchronous receive (`recv()`, `recv_msg()`, `recv_into()`) on a socket or context now keeps one receive in flight until it completes, times out, or is interrupted. Before, it cancelled and restarted the receive every 100 ms, which ends a `Req0` request and a `Surveyor0` survey: a `Req0` receive on a socket or a context whose reply took longer than 100 ms raised `BadState`, and after about 100 ms a `Surveyor0` receive raised `Timeout` on a socket and `BadState` on a context, whatever the `survey_time`. Ctrl-C still interrupts a blocking receive
- `Socket.close()` called from a pipe callback now returns at once, and the socket is closed on another thread when the running pipe callbacks have returned. Before, a close from a socket's own `post_pipe_connect` callback, or from a `post_pipe_remove` callback when no other thread was closing the socket, never returned

### Fixed
- Prevent removed pipes from staying in `Socket.pipes` with nng v1: when `NNG_PIPE_EV_REM_POST` from the reaper thread reaches Python before `NNG_PIPE_EV_ADD_PRE` or `NNG_PIPE_EV_ADD_POST` for the same pipe, the late event is now dropped, so it no longer adds the pipe back or runs `post_pipe_connect` callbacks after `post_pipe_remove` callbacks. A message received from a removed pipe also no longer adds the pipe back
- Prevent a deadlock with nng v2 when a pipe callback reads `Socket.pipes`: v2 pipe callbacks now run without the socket's pipe lock held, as v1 callbacks already did
- Apply `Sub0(topics=...)` before `listen`/`dial`, so messages that arrive just after the connection is made are no longer dropped before the subscription exists
- Prevent a deadlock when garbage collection finalizes an unclosed `Socket`, `Context`, `AIOHelper` or `DeviceAIO` while the same thread is registering or closing a socket or an AIO: the `_active_handles` and `_aio_map` registries no longer use locks, because a finalizer can run while its thread holds one
- Prevent a double free of the message when `Socket.send_msg()` or `Context.send_msg()` is interrupted (for example, by Ctrl-C) during a send. The `Message` now gives up ownership before nng can take the message, and takes it back only if nng did not consume it. An interruption just after a failed send can leak the message, but it cannot free it twice
- Prevent a use-after-free in the asyncio completion queue when `MPSCAIOEngine` is garbage-collected before the `AIOHelper` or `DeviceAIO` objects that use its queue. Each entry now holds a reference on the C queue, and the last reference frees it
- Write the wake-up byte of the completion queue while the queue lock is held, so a completion that races with `MPSCAIOEngine.close()` cannot write to the wake-up pipe after its file descriptor is closed and possibly reused
- Prevent `MPSCAIOEngine.register()` from reusing a slot id that is still pending when the 31-bit slot counter (mask `0x7FFFFFFF`) wraps around
- `Rep0Service` workers no longer log an exception each time `recv_timeout` expires with no request
- `Socket.asend_msg()`, `Socket.arecv_msg()`, `Context.asend_msg()` and `Context.arecv_msg()` (and so `arecv()`, `arecv_into()` and `async for`) now raise `RuntimeError` in a forked child, as the synchronous operations already did
- Fix #108: Prevent process crash / NNG panic during Python interpreter shutdown by disabling unconditional `nng_fini()` at atexit (`nng_fini_at_exit = False`) and guarding `Socket`, `Context`, `Message`, `AIOHelper`, and `DeviceAIO` finalizers against calling deallocated NNG C state during GC
- Fix #113: Prevent hard C aborts (`panic: nng is not fork-reentrant safe`) in forked child processes by detecting `fork()` and raising a descriptive Python `RuntimeError` directing users to `multiprocessing.set_start_method('spawn')`
- Fix #104: Prevent `RuntimeError: cannot use unpack() on <cdata 'char *' NULL>` when receiving 0-byte messages via v1 `Socket.recv()`
- Fix #128: Ensure `asyncio.CancelledError` is always propagated by `wait_for_aio()` if task was cancelled, preventing swallowed cancellations and freeing orphaned messages during cancel/send races
- `ffi.from_handle` dangling pointer in pipe callbacks: module-level `_active_handles` registry keeps handles alive until `Socket.close()` completes, with try/except guard in `_nng_pipe_cb`
- `_aio_map` thread safety for free-threaded Python (3.13t/3.14t): every access is a single dict operation, which is atomic without the GIL
- `AIOHelper._free()` potential deadlock during GC: cancel pending AIO operations before calling `nng_aio_free()` to prevent callback/GIL deadlock
- Pipe callback list mutations now protected by `_pipe_notify_lock` for thread safety under free-threaded Python
- Make `Socket.close()` idempotent and thread-safe with `_close_lock` and `_socket_closed` flag
- `_setopt_size` and `_setopt_ms` now check error returns from NNG C library instead of silently swallowing failures
- `Message._buffer` raises `MessageStateError` after send instead of returning `None` (which caused confusing `TypeError`)
- `_NNGOption.__get__` error message corrected from "cannot be set" to "is write-only"
- `TLSConfig` constructor now correctly applies `AUTH_MODE_NONE` (value 0) instead of silently skipping it
- Thread-safety of `pipes` property for free-threaded Python (3.14t)
- `__del__` guards for `Socket`, `Context`, and `TlsConfig` to prevent tracebacks during interpreter shutdown
- `TLS.set_server_name` validation allows empty string (valid for clearing) and rejects `None` with clear error

[unreleased]: https://github.com/codypiersall/pynng/compare/v0.9.0...HEAD
