# Roadmap

This document outlines the planned direction, active initiatives, architectural evolutions, and future horizons for **pynng**.

> **Status & Priorities**: Priorities are reviewed regularly and evolve based on upstream NNG development, Python CPython lifecycle milestones (such as PEP releases and EOLs), and community requirements.
>
> **Want to get involved?** We welcome contributions! If you're looking for areas to contribute, check out the items in **Near-Term** and **Medium-Term** below, or open a discussion on GitHub. Please review our [Contributing Guide](CONTRIBUTING.md) to get set up with our modern build and development environment.

---

## Project Philosophy

`pynng` provides ergonomic, high-performance Python bindings to the [NNG (nanomsg-next-generation)](https://github.com/nanomsg/nng) messaging library. The library's core values are:

- **Zero-GIL Concurrency**: Native operations, asynchronous callbacks, and I/O execution run without locking the Python interpreter whenever possible.
- **Asyncio & Trio First-Class Support**: Seamless, ergonomic integration with Python's asynchronous ecosystems (`asyncio`, `trio`, and `anyio`).
- **Memory Safety & Resource Determinism**: Guaranteed cleanup of native sockets, contexts, dialers, listeners, and messages without leaks or race conditions during finalization or garbage collection.
- **Turnkey Multi-Platform Packaging**: Pre-built binary wheels across Linux (x86_64, aarch64), macOS (universal2 / arm64 / x86_64), and Windows (x64, ARM64) with batteries-included TLS support.

---

## Active & Upcoming Horizons

### 🟡 Near-Term (v1.0.0 / Immediate Release Horizon)

#### 1. NNG v2 Endpoint URL Resolution & Diagnostics
- Fix `v2.Dialer.url` and `v2.Listener.url` by calling `nng_dialer_get_url()` and `nng_listener_get_url()`, replacing the removed `NNG_OPT_URL` option.
- Add helper properties for dynamic port and address resolution on ephemeral bindings (`tcp://127.0.0.1:0`).

#### 2. NNG v2 TLS Endpoint Configuration & FFI Bridging
- Enable passing `pynng.TLSConfig` directly to v2 sockets, listeners, and dialers (`listen(..., tls_config=...)`, `dial(..., tls_config=...)`).
- Expose `tls_config` getter/setter on `v2.Listener` and `v2.Dialer` using `nng_listener_set_tls()` and `nng_dialer_set_tls()`.
- Unify internal FFI representations so `TLSConfig` instances can be seamlessly applied to both v1 and v2 native endpoints without CFFI type mismatch.
- Add dedicated `test/test_v2_tls.py` suite covering TLS client/server negotiation in v2.

#### 3. Upstream NNG v1 Bugfix Revision Bump
- Bump v1 CMake `NNG_REV` from `v1.11` to `v1.12.3` to incorporate upstream fixes for large IOV scatter/gather transfers and platform-specific socket edge cases.

---

### 🟢 Medium-Term

#### 4. Retirement of Python 3.10 Support
*Python 3.10 reached official End-of-Life (EOL) in October 2026. Support will be phased out in an upcoming release.*

- **Packaging & Metadata**:
  - Bump `requires-python` in `pyproject.toml` from `>=3.10` to `>=3.11`.
  - Remove `"Programming Language :: Python :: 3.10"` classifier.
  - Update `scikit-build-core` configuration: set `wheel.py-api = "cp311"` in `pyproject.toml`.
  - Update CMake configuration: set `USE_SABI 3.11` for `_nng` and `_nng_v2` extension targets in `CMakeLists.txt`.
- **CI & Build Matrix Pruning**:
  - Remove Python 3.10 from `.github/workflows/smoketest.yml` matrix.
  - Remove `cp310-*` from `cibuildwheel` targets in `.github/workflows/cibuildwheel.yml` and `pyproject.toml`.
  - Update `.pre-commit-config.yaml` language environment to Python 3.11.
- **Modern Language & Standard Library Adoption (3.11+)**:
  - **Standard library `tomllib`**: Use built-in `tomllib` directly without external fallbacks.
  - **`typing.Self`**: Adopt `typing.Self` for fluent builders, context managers, and method chaining across socket and context classes.
  - **`asyncio.TaskGroup`**: Refactor internal multi-task operations and test harnesses to use structured concurrency.
  - **`ExceptionGroup` & `except*`**: Handle multi-socket teardowns and concurrent errors cleanly.
  - **PEP 659 Specialized Adaptive Interpreter**: Leverage Python 3.11+ bytecode specializations across hot message passing and AIO completion loops.

#### 5. NNG v2 Extended Transports & Socket Activation
- **`udp://` & `dtls://` Transport Support**: Expose NNG v2 datagram and datagram-TLS options (`peer-expiry`, `peer-limit`, `retry-time`).
- **`winpipe://` on Windows**: Expose Windows named pipes under v2 (since v2 `ipc://` transitioned to standard `AF_UNIX`).
- **Socket Activation / FD Passing**: Expose `NNG_OPT_LISTEN_FD` (`socket://`) for systemd, launchd, or pre-bound socket inheritance.

#### 6. Windows Wait-Free IOCP Asyncio Integration
- Currently, wait-free C11 MPSC queue dispatch relies on `loop.add_reader`, which POSIX asyncio event loops and `SelectorEventLoop` provide. On Windows `ProactorEventLoop`, pynng seamlessly falls back to thread-safe callback scheduling (`loop.call_soon_threadsafe`).
- Investigate native IOCP or Windows completion routines integration to enable wait-free MPSC zero-GIL dispatching on Windows `ProactorEventLoop`.

#### 7. Zero-Copy Streaming Pipe Protocol (`nng_stream`)
- Expose the raw byte-stream API (`nng_stream_dialer`, `nng_stream_listener`, `nng_stream`) for non-SP protocols (raw byte-level TLS/TCP streaming).

---

### 🔵 Long-Term & Exploratory

#### 8. Structured Message Codecs & RPC Layer
- High-level request/response streaming and pipelining patterns.
- First-class plugin interfaces for zero-copy schema serialization (MsgPack, FlatBuffers, Cap'n Proto, Protobuf).

#### 9. Pure Python Fallback / Static WebAssembly (Wasm/Pyodide)
- Investigate Pyodide / Emscripten builds using WebSockets transport (`ws://` and `wss://`).

---

## Completed Milestones (Since v0.9.0)

### 1. Build Modernization & Dual-Version Architecture
- [x] **Scikit-Build-Core Build Backend**: Migrated from legacy `setup.py` / `setuptools` to `scikit-build-core` and PEP 517.
- [x] **Automated CFFI Generation via Headerkit**: Replaced fragile handwritten CFFI bindings with automated parsing and header generation via `headerkit`.
- [x] **NNG v2.0.0 Dual-Version Coexistence**: Full dual-module architecture supporting nng v2.0.0 GA alongside v1 under `pynng.v2` and `_nng_v2`.
- [x] **Multi-Platform cibuildwheel Matrix**: Universal automated wheel generation and testing across Linux (x86_64, aarch64), macOS (universal2), and Windows (x64, arm64).

### 2. High-Performance Concurrency & Zero-GIL Async
- [x] **Wait-Free C11 MPSC AIO Queue & Helper Pooling**: Integrated Dmitry Vyukov wait-free intrusive MPSC completion queue for zero-GIL async dispatching and 2x throughput speedups (PR #195).
- [x] **C11 Atomics on MSVC & Windows**: Configured `/std:c11 /experimental:c11atomics` for Visual Studio MSVC compilers, enabling cross-platform C11 atomics (PR #205).
- [x] **Free-Threaded CPython Support**: Hardened against GIL-less execution and validated under PEP 703 (Python 3.13t & 3.14t) with `.venv-freethreaded` support.
- [x] **Non-Blocking Ergonomics**: Added `recv_nowait()`, `send_nowait()`, `recv_msg_nowait()`, `send_msg_nowait()`, and `recv_into_nowait()` on `Socket` and `Context` (PR #194).
- [x] **Object Memory Footprint Optimization**: Enabled `__slots__` across `Message`, `Request`, `Stat`, and `SockAddr` hot-path models (PR #193).

### 3. Protocol Ergonomics & High-Level Services
- [x] **`Rep0Service` High-Level Service**: Concurrent request/reply handling with dedicated context workers and clean shutdown semantics.
- [x] **`Surveyor0.asurvey()` Async Collector**: Ergonomic survey-and-collect helper collecting responses until timeout or response limits.
- [x] **Async Context Managers & Iterators**: Full `async with` and `async for` support across `Socket`, `Dialer`, and `Listener`.
- [x] **Async Pipe Event Streams**: `socket.pipe_events()` async iterator for monitoring connect and disconnect events.
- [x] **`Sub0` Local Subscription Tracking**: Added `subscriptions` inspection, `subscribe_all()`, and `unsubscribe_all()` batch management.

### 4. Raw Sockets, Devices & Low-Level Extensions
- [x] **Raw Socket Classes**: Added `RawBus0`, `RawPair0`, `RawPair1`, `RawReq0`, `RawRep0`, etc., for custom protocol proxies and brokers.
- [x] **Kernel Forwarding Proxies**: Added `pynng.device()` and async `pynng.adevice()` forwarding proxies.
- [x] **Zero-Copy Buffer Protocol**: Full `Py_buffer` / `memoryview` support for direct DMA/socket transmission without copying (`recv_into`, `arecv_into`).
- [x] **Message Header Manipulation**: Added `msg.header`, `msg.header_insert()`, `msg.header_append()`, `msg.header_trim()`, and `msg.header_chop()`.
- [x] **Runtime Statistics**: Exposed NNG internal diagnostics via `pynng.stats()` and `socket.get_stat()`.
