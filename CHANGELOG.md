# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- `async with` context manager support for sockets (`async with pynng.Pair0() as sock:`)
- `async for` iteration over received messages (`async for msg in sock:`)
- `aclose()` method for explicit async socket cleanup
- `async with` context manager support for `Dialer` and `Listener`
- `aclose()` method for `Dialer` and `Listener`
- `recv_timeout` and `send_timeout` option descriptors on `Context` for per-context timeout control

### Changed
- Switch cibuildwheel to uv build frontend, eliminating virtualenv.pyz downloads
- Migrate build system from setuptools/CMake to scikit-build-core with headerkit for C header generation
- Replace handwritten CFFI bindings with auto-generated bindings from NNG headers via headerkit
- Add CI concurrency groups to cancel stale workflow runs
- Scope cibuildwheel tests to exclude build-system tests (run in smoketest instead)

### Fixed
- `_setopt_size` and `_setopt_ms` now check error returns from NNG C library instead of silently swallowing failures
- `Message._buffer` raises `MessageStateError` after send instead of returning `None` (which caused confusing `TypeError`)
- `_NNGOption.__get__` error message corrected from "cannot be set" to "is write-only"
- `TLSConfig` constructor now correctly applies `AUTH_MODE_NONE` (value 0) instead of silently skipping it
- Thread-safety of `pipes` property for free-threaded Python (3.14t)
- `__del__` guards for `Socket`, `Context`, and `TlsConfig` to prevent tracebacks during interpreter shutdown
- `TLS.set_server_name` validation allows empty string (valid for clearing) and rejects `None` with clear error

[unreleased]: https://github.com/codypiersall/pynng/compare/v0.9.0...HEAD
