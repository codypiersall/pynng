# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.0.0b4] - 2026-11-13

### Added
- Pre-generate and track `pynng/_nng_cdef.py` (`CDEF_V1_TLS`, `CDEF_V1_NO_TLS`, `CDEF_V2_TLS`, `CDEF_V2_NO_TLS`, and `get_cached_cdef()`, loaded directly via `importlib.util.spec_from_file_location` in `build_pynng.py` and refreshed in-place when `PYNNG_USE_CACHED_CDEF=0`) so clean PEP 517 builds can emit CFFI C sources without requiring `headerkit`, `libclang`, or pre-compiled `pynng._nng`, and automated NNG bump PRs in `.github/workflows/check-nng.yml` regenerate and stage `pynng/_nng_cdef.py` alongside `pynng/_nng.pyi` and `pynng/_nng_v2.pyi`
- Auto-detect pre-populated in-tree `mbedtls/`, `wolfssl/`, `nng/`, and `nng_v2/` source directories and support `MBEDTLS_SOURCE_DIR`, `WOLFSSL_SOURCE_DIR`, `NNG_SOURCE_DIR`, and `NNG_V2_SOURCE_DIR` in `CMakeLists.txt` (normalized to absolute paths and cached in `FETCHCONTENT_SOURCE_DIR_*` with `CACHE PATH ... FORCE`) for offline distro builds (`pkgsrc`, `nixpkgs`, `AUR`)

### Changed
- Remove `cffi_buildtool` and `headerkit` from `[build-system].requires` and `cibuildwheel` `before-build` hooks in `pyproject.toml`, add full PEP 484 type annotations to `build_pynng.py`, and invoke `build_pynng.py <output_c_file>` (`ffibuilder.emit_c_code()`) directly from `CMakeLists.txt`
- Consolidate duplicate `Socket.recv`, `Socket.send`, `Socket.arecv`, and `Socket.asend` implementations onto `pynng._base.Socket`, remove unused `cmake/idempotent_patch.cmake` and `docs/snippets/pair{0,1}_async.py`, clean up stale `patches/**` workflow triggers and cache keys, and add `src/**` and `CMakeLists.txt` triggers to `benchmarks.yml`
- Update `README.md`, `ROADMAP.md`, `CONTRIBUTING.md`, `examples/`, and Sphinx documentation (`docs/architecture.rst`, `docs/contributing.rst`, `docs/developing.rst`, `docs/getting-started.rst`, `docs/installation.rst`, `docs/migration.rst`, `docs/api/service.rst`, `docs/api/sockets.rst`, `docs/api/v2.rst`, and `docs/make.bat`)

### Fixed
- Fix `ZTAddr` (`pynng/sockaddr.py`) reading nonexistent `as_nwid`, `as_nodeid`, and `as_port` attributes instead of `sa_nwid`, `sa_nodeid`, and `sa_port` on `nng_sockaddr_zt`, format `ZTAddr.__str__()` as `zt://<nodeid:010x>.<nwid:016x>:<port>`, define `family_as_str` on all concrete `SockAddr` subclasses (resolving family constants against the active `_lib`), decode `AbstractAddr.name` without double-unquoting raw bytes, and store the active `ffi` and `lib` on `SockAddr`
- Pass the active `lib` and `ffi` instances to `_nng_sockaddr()` in `_getopt_sockaddr()` and `pynng.v2.Pipe`, resolve stat type/unit names dynamically from the active `lib` in `pynng/stats.py` (with `Stat.__getitem__()` checking direct `children` first and `_STAT_ATTRS` second without returning bound methods, and `Socket.stat()` looking up direct child stats), and pass `lib` and `ffi` to all `check_err()` calls across `pynng/options.py`, `pynng/_base.py`, and `pynng/v2/nng.py` so NNG v2 `abstract://` addresses, statistics, and error codes resolve against the v2 library
- Track active surveys via `_survey_active` on `Surveyor0` (`pynng/nng.py` and `pynng/v2/nng.py`) and validate outgoing data/messages before setting `_survey_active = True` so calling `recv()` or `arecv()` without an active survey raises `BadState` consistently across v1 and v2 while calling `recv()` or `arecv()` after `survey_time` has expired raises `Timeout` on the first call and `BadState` on subsequent calls
- Wake `_replied_event` safely across threads via `loop.call_soon_threadsafe()` (asyncio) or `trio_token.run_sync_soon()` (Trio), validate `workers >= 1` (rejecting `bool`), clean up spawned tasks and contexts if `Rep0Service.__aenter__()` fails, suppress false `ResourceWarning`s for unyielded queued `Request` objects by arming `_replied = False` in `Rep0Service.__anext__()`, and guard against uninitialized instances in `Request.__del__()` (`pynng/service.py`)
- Guard `Message.pipe` setter and `asend_msg()` with `_mem_freed_lock` (releasing the lock before `await` and restoring `_mem_freed = False` if send fails before NNG takes ownership), guard `Context.close()` with `_close_lock` and `_ctx_closed` while tolerating `NNG_ECLOSED` when the parent socket has already closed, register `start=False` dialers and listeners in `Socket._dialers` / `Socket._listeners` (and lazily wrap unknown dialer/listener IDs in `Pipe.dialer` / `Pipe.listener`), and make `Sub0` topic tracking (`_subscriptions`) atomic under `_sub_lock` across v1 and v2
- Cancel and wait on in-flight `nng_aio` operations in `except BaseException:` inside `_wait_for_aio()` before freeing messages in `AIOHelper` (and guard `if (!r->done)` before `nng_aio_cancel()` / `nng_aio_wait()` in `pynng_sync_recv_free()`), call `_mark_nng_initialized()` at `import pynng.v2` and in `TLSConfig.__init__()` so `os.fork()` in child processes raises `RuntimeError` instead of aborting in C, break `Socket`/`Context` <-> `AIOHelper` reference cycles via `_obj_ref` (`weakref.ref(obj)`), mark participating v2 `Socket` wrappers closed after `nng_device_aio` closes their underlying C sockets (probing `nng_socket_raw() == NNG_ECLOSED` in `_mark_v2_device_owners_closed()`), cache unsupported event loops in `MPSCAIOEngine.get_for_loop()`, and pass the active `lib` to `is_nng_finalized(lib)` so `pynng.nng_fini()` and `pynng.v2.nng_fini()` track `_finalized` independently per library
- Hide statically linked NNG, mbedTLS, and wolfSSL symbols in `_nng` and `_nng_v2` (`-fvisibility=hidden`, `-Wl,-exported_symbol,*[Ii]nit__nng` / `*[Ii]nit__nng_v2` on macOS for CPython and PyPy, `-Wl,--exclude-libs,ALL` on Linux, and `SCCACHE_CACHE_MULTIARCH=1` on macOS in `cibuildwheel.yml`) so loading both extensions in one process cannot cause C symbol collisions, pass `-DCMAKE_FIND_PACKAGE_PREFER_CONFIG=FALSE` for staged mbedTLS in `nng_v2_build`, forward cross-compilation and compiler flags to `nng_v2_build`, and avoid unlinking active flock lockfiles in `build_pynng.py`
- Size `_setopt_string_nonnull` buffers by UTF-8 byte length (`len(val_bytes)`), validate `TLSConfig` auth modes before mutating state, and free partially initialized `TLSConfig` handles via `_free_configs()` on constructor error
- Annotate void `nng_recv_aio`, `nng_send_aio`, `nng_ctx_recv`, and `nng_ctx_send` functions as returning `None` in `_AioLibProtocol` and `_BaseLibProtocol`, and keep `NNG_PATCH_VERSION = 4` in `pynng/_nng_cdef.py` and `pynng/_nng.pyi` to match upstream `nanomsg/nng` `v1.12.5` `include/nng/nng.h`
- Make `PipeEvent` (`NamedTuple, Generic[_PipeT]`) and `PipeEventStream` (`Generic[_PipeT, _PipeEventT]`) generic over covariant `_PipeT` and `_PipeEventT` (preserving full `NamedTuple` methods `_asdict()`, `_replace()`, `_fields`, `_field_defaults`, positional pattern matching, tuple unpacking, and indexing on `PipeEvent`), provide module-narrowed `PipeEvent` and `PipeEventStream` subclasses in `pynng` and `pynng.v2` without `TYPE_CHECKING` stream method overrides, and narrow `Socket.add_pre_pipe_connect_cb()`, `add_post_pipe_connect_cb()`, `add_post_pipe_remove_cb()`, `remove_pre_pipe_connect_cb()`, `remove_post_pipe_connect_cb()`, `remove_post_pipe_remove_cb()`, and `pipe_events()` on `pynng.Socket` and `pynng.v2.Socket` so both unparameterized annotations and callbacks typed with `pynng.Pipe` or `pynng.v2.Pipe` pass `mypy --strict` and `pyright` without errors

## [1.0.0b3] - 2026-11-10

### Added
- Add inline PEP 484 type annotations across all `pynng` and `pynng.v2` Python modules, ship the PEP 561 `pynng/py.typed` marker in built wheels, and narrow v1/v2 `Socket`, `Context`, `Pipe`, and `Message` return types for `mypy --strict` consumers
- Generate and install zero-`Any` PEP 484 `_nng.pyi` and `_nng_v2.pyi` type stubs into built wheels via `CMakeLists.txt`, and define explicit `__all__` exports on `pynng`, `pynng.nng`, `pynng.v2`, and `pynng.v2.nng`

### Changed
- Migrate `build_pynng.py` to `headerkit~=0.51.0` (`CffiWriter` and `PyiWriter(mode="cffi")`), removing the runtime `headerkit._clang` monkey-patch loader, regex `cdef` post-processing, `_extract_defines()`, dummy enum tag workarounds, and `-Wno-incompatible-pointer-types` compiler flags in `CMakeLists.txt`
- Parse `src/aio_engine.h` C declarations (including `_async_complete` and `_nng_pipe_cb` callback prototypes) directly via `libclang` (`#define PYNNG_CFFI_CDEF`) in `_parse_nng_headers()` and memoize the parsed `Header` IR so `CffiWriter` and `PyiWriter(mode="cffi")` share a single `libclang` parse pass per target and emit 1:1 matching `_nng.pyi` / `_nng_v2.pyi` stubs natively (using `_BUILD_SCRIPT` so `cffi_buildtool exec-python` succeeds when `__file__` is absent from `globals()`)

## [1.0.0b2] - 2026-10-31

### Added
- Upgrade bundled nng v2 from `v2.0.0` to `v2.1.0`, adding DTLS 1.2/1.3 (`dtls://`, `dtls4://`, `dtls6://`) transport support in `pynng.v2` (`Socket`, `Dialer`, `Listener`, `Pipe.scheme == "dtls"`, and `TLSConfig`)
- `-DPYNNG_USE_LATEST_PATCH=ON` CMake option to automatically resolve `NNG_REV` and `NNG_V2_REV` to the latest upstream patch tag in their respective `major.minor` series at configure time, with a monotonicity guard that prevents downgrades if a mirror lags behind
- Dual-track automated NNG release check workflow (`scripts/check_nng_updates.py` and `.github/workflows/check-nng.yml`) monitoring both `v1.x` (`NNG_REV`) and `v2.x` (`NNG_V2_REV`), opening automated bump PRs for verified patch releases and tracking issues for minor/major releases or pre-releases

### Changed
- Upgrade bundled `wolfSSL` from `v5.8.2-stable` to `v5.9.4-stable` when building with `-DPYNNG_TLS_ENGINE=wolf`, enabling TLS 1.3 and DTLS 1.2/1.3 (`WOLFSSL_DTLS=yes`, `WOLFSSL_DTLS13=yes`, `WOLFSSL_DTLS_MTU=yes`, `WOLFSSL_DTLS_CID=yes`) and staging a `wolfssl-config.cmake` package config for `nng v2`
- Pin `headerkit~=0.49.4` across `pyproject.toml` build requirements, optional `dev` dependencies, and `cibuildwheel` `before-build` hooks to allow patch updates while preventing unverified breaking minor releases
- Update documentation across `README.md`, `docs/installation.rst`, `docs/tls.rst`, `docs/transports.rst`, `docs/developing.rst`, and `docs/architecture.rst` for NNG v2.1.0, DTLS 1.2/1.3, `PYNNG_TLS_ENGINE`, `PYNNG_USE_LATEST_PATCH`, and CFFI API-mode extension architecture

### Fixed
- Fix `RawSurveyor0.recv()` / `Surveyor0(raw=True).recv()` raising `NotSupported` by removing the vestigial `survey_time` read in `Socket.recv_msg()`
- Return `"abstract"` from `AbstractAddr.family_as_str` on nng v2
- Check for `fork()` in `Message._ensure_can_send()` so `Socket.send_msg()` and `Context.send_msg()` reject inherited handles in forked children

## [1.0.0b1] - 2026-10-27

### Added
- Non-blocking convenience methods on both `Socket` and `Context`: `recv_nowait()`, `send_nowait()`, `recv_msg_nowait()`, `send_msg_nowait()`, and `recv_into_nowait()`
- High-performance wait-free C11 MPSC intrusive queue engine and helper pooling for zero-GIL async I/O completions and up to 2x throughput speedups
- Hardened performance benchmark suite with GC-pause isolation, best-of-N multi-trial execution, and TCP nodelay optimization for reproducible CI measurement
- Dual-version coexistence with nng v2.0.0 GA under the `pynng.v2` namespace (`pynng.v2.Bus0`, `pynng.v2.Req0`, `pynng.v2.Rep0`, `pynng.v2.Pair0`, `pynng.v2.Pair1`, `pynng.v2.Pub0`, `pynng.v2.Sub0`, `pynng.v2.Push0`, `pynng.v2.Pull0`, `pynng.v2.Surveyor0`, `pynng.v2.Respondent0`)
- Pluggable TLS engine support via CMake `PYNNG_TLS_ENGINE` supporting `mbed` (`mbedTLS`), `wolf` (`wolfSSL`), `openssl` (`OpenSSL`), and `none`
- Raw socket wrapper classes (`RawBus0`, `RawPair0`, `RawPair1`, `RawReq0`, `RawRep0`, `RawPub0`, `RawSub0`, `RawPush0`, `RawPull0`, `RawSurveyor0`, `RawRespondent0`) for broker and proxy topologies
- `pynng.device()` and async `pynng.adevice()` forwarding proxies for kernel-level bridging
- Zero-copy Python buffer protocol support (`Socket.recv_into`, `Socket.arecv_into`, memoryview/bytearray send) across both v1 and v2
- Message header manipulation and inspection (`Message.header`, `msg.header_insert()`, `msg.header_append()`, `msg.header_trim()`, `msg.header_chop()`)
- Runtime statistics extraction via `pynng.stats()`, `pynng.socket_stats()`, and `socket.stat()`
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
- `pynng.v2.device()` and `pynng.v2.adevice()`. `pynng.device()` and `pynng.adevice()` also accept nng v2 sockets. Closing a socket that a device uses ends the device with `Closed`, also with nng v2, which otherwise refuses to close a socket that a device owns
- nng v2 statistics: `pynng.v2.stats()`, `pynng.v2.socket_stats()`, `pynng.v2.Socket.stats()` and `pynng.v2.Socket.stat()`, and `pynng.v2.Stat`. The bundled nng v2 is now built with statistics enabled
- Endpoint TLS for nng v2: `tls_config=` on `pynng.v2.Socket.dial()` and `listen()`, `pynng.v2.Dialer.tls_config` and `pynng.v2.Listener.tls_config`, and `pynng.v2.Socket.tls_config` (the default for the socket's endpoints; endpoints whose transport has no TLS ignore it, as in v1). One `TLSConfig` can be used with both v1 and v2 endpoints
- `start=False` on `pynng.v2.Socket.dial()` and `listen()`, with `pynng.v2.Dialer.start()` and `pynng.v2.Listener.start()` to start the endpoint later
- `pynng.v2.Dialer.url` and `pynng.v2.Listener.url`
- The raw classes `pynng.v2.RawBus0`, `RawPair0`, `RawPair1`, `RawPush0`, `RawPull0`, `RawPub0`, `RawSub0`, `RawReq0`, `RawRep0`, `RawSurveyor0` and `RawRespondent0`
- `socket=` argument of `Rep0Service` (v1 and v2), to serve on an existing `Rep0` socket that the service does not close. `address` is optional when `socket` is given. The service closes the listener it made for `address` and restores the socket's timeouts on exit. A socket that is not a non-raw `Rep0` of the service's nng version raises `TypeError` or `ValueError`

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
- Add a `sanitizers` CI workflow that builds nng v1, nng v2 and the cffi extensions with AddressSanitizer and UndefinedBehaviorSanitizer and runs the test suite under them on Linux
- `post_pipe_remove` callbacks for a pipe now wait until the running `pre_pipe_connect` and `post_pipe_connect` callbacks for that pipe return, so a remove callback no longer runs at the same time as a connect callback for the same pipe
- A synchronous receive (`recv()`, `recv_msg()`, `recv_into()`) on a socket or context now keeps one receive in flight until it completes, times out, or is interrupted. Before, it cancelled and restarted the receive every 100 ms, which ends a `Req0` request and a `Surveyor0` survey: a `Req0` receive on a socket or a context whose reply took longer than 100 ms raised `BadState`, and after about 100 ms a `Surveyor0` receive raised `Timeout` on a socket and `BadState` on a context, whatever the `survey_time`. Ctrl-C still interrupts a blocking receive
- `pynng.v2.TLSConfig` is now a subclass of `pynng.TLSConfig` that allocates its configuration with nng v2. Before, it was `pynng.TLSConfig`
- A `TLSConfig` now allocates a configuration for each initialized nng version (v1, and v2 when `pynng.v2` is imported) when it is created, and each setter changes all of them. A `pynng.TLSConfig` created before `pynng.v2` is imported cannot be used with v2 endpoints (`RuntimeError`). When a setter succeeds for one version and fails for another, the config cannot be used with the failed version any more (`RuntimeError`)
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
- `pynng.v2.Surveyor0.asurvey()` no longer raises `NameError` when the survey times out
- `pynng.v2.Rep0Service` now uses a `pynng.v2.Rep0` socket. Before, it was `pynng.Rep0Service`, which uses an nng v1 socket
- `pynng.v2.Pipe.local_address` and `remote_address` no longer raise `AttributeError` for an `abstract://` pipe
- `raw=True` on a `pynng.v2` protocol class now opens a raw socket. Before, it was ignored
- `pynng.nng_fini_at_exit = True` now makes pynng call `nng_fini()` at exit. Before, only `pynng.nng.nng_fini_at_exit = True` had an effect
- Fix #108: Prevent process crash / NNG panic during Python interpreter shutdown by disabling unconditional `nng_fini()` at atexit (`nng_fini_at_exit = False`) and guarding `Socket`, `Context`, `Message`, `AIOHelper`, and `DeviceAIO` finalizers against calling deallocated NNG C state during GC
- Fix #113: Prevent hard C aborts (`panic: nng is not fork-reentrant safe`) in forked child processes by detecting `fork()` and raising a descriptive Python `RuntimeError` directing users to `multiprocessing.set_start_method('spawn')`
- Fix #104: Prevent `RuntimeError: cannot use unpack() on <cdata 'char *' NULL>` when receiving 0-byte messages via v1 `Socket.recv()`
- Fix #128: Ensure `asyncio.CancelledError` is always propagated by `wait_for_aio()` if task was cancelled, preventing swallowed cancellations and freeing orphaned messages during cancel/send races
- `ffi.from_handle` dangling pointer in pipe callbacks: module-level `_active_handles` registry keeps handles alive until `Socket.close()` completes, with try/except guard in `_nng_pipe_cb`
- `_aio_map` thread safety for free-threaded Python (3.13t/3.14t): every access is a single dict operation, which is atomic without the GIL
- `AIOHelper._free()` potential deadlock during GC: cancel pending AIO operations before calling `nng_aio_free()` to prevent callback/GIL deadlock
- Pipe callback list mutations now protected by `_pipe_notify_lock` for thread safety under free-threaded Python
- Make `Socket.close()` idempotent and thread-safe with `_close_lock` and `_socket_closed` flag
- Harden test suite against race conditions on free-threaded builds (coroutine cleanup on Windows, respondent post-connect wait) and ensure `wait_pipe_len()` waits until protocols have fully started connected pipes before sending messages
- `_setopt_size` and `_setopt_ms` now check error returns from NNG C library instead of silently swallowing failures
- `Message._buffer` raises `MessageStateError` after send instead of returning `None` (which caused confusing `TypeError`)
- `_NNGOption.__get__` error message corrected from "cannot be set" to "is write-only"
- `TLSConfig` constructor now correctly applies `AUTH_MODE_NONE` (value 0) instead of silently skipping it
- Thread-safety of `pipes` property for free-threaded Python (3.14t)
- `__del__` guards for `Socket`, `Context`, and `TlsConfig` to prevent tracebacks during interpreter shutdown
- `TLS.set_server_name` validation allows empty string (valid for clearing) and rejects `None` with clear error

[unreleased]: https://github.com/codypiersall/pynng/compare/v1.0.0b4...HEAD
[1.0.0b4]: https://github.com/codypiersall/pynng/compare/v1.0.0b3...v1.0.0b4
[1.0.0b3]: https://github.com/codypiersall/pynng/compare/v1.0.0b2...v1.0.0b3
[1.0.0b2]: https://github.com/codypiersall/pynng/compare/v1.0.0b1...v1.0.0b2
[1.0.0b1]: https://github.com/codypiersall/pynng/compare/v0.9.0...v1.0.0b1
