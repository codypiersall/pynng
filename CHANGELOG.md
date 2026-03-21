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

[unreleased]: https://github.com/codypiersall/pynng/compare/v0.9.0...HEAD
