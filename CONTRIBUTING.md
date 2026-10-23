# Contributing to pynng

Thank you for your interest in contributing to pynng! This guide will help you
get set up for development and walk you through the contribution workflow.

## Getting Started

### Where to Contribute

Looking for a place to start?

- **GitHub Issues**: Browsing open [GitHub Issues](https://github.com/codypiersall/pynng/issues) is a great place to start, especially issues labeled [`good first issue`](https://github.com/codypiersall/pynng/issues?q=is%3Aissue+is%3Aopen+label%3A%22good+first+issue%22) or [`help wanted`](https://github.com/codypiersall/pynng/issues?q=is%3Aissue+is%3Aopen+label%3A%22help+wanted%22). If you find a bug or have a suggestion, feel free to open a new issue to discuss it first.
- **Project Roadmap**: Check out our [Roadmap](ROADMAP.md) for prioritized near-term features, bug fixes, and architectural goals across both NNG v1 and v2 runtimes.
- **Discussions**: Start or join conversations in GitHub Discussions or existing issue threads to coordinate before submitting large PRs.

### Prerequisites

- Python 3.10+
- CMake 3.26+
- ninja-build
- libclang (for building from source -- headerkit uses it to parse NNG's C headers)
  - Recommended: `python -m headerkit.install_libclang` (works across platforms without root)
  - Or via system packages:
    - Ubuntu/Debian: `sudo apt install ninja-build libclang-dev`
    - macOS: Xcode command line tools (usually sufficient)
    - RHEL/CentOS/Fedora: `sudo dnf install clang-devel`
    - Alpine: `apk add clang-dev`
    - Windows: LLVM (or via `python -m headerkit.install_libclang`)

### Development Setup

```bash
git clone https://github.com/codypiersall/pynng
cd pynng
pip install uv                      # if you don't have uv yet
uv pip install -e '.[dev]'
pre-commit install
```

This will:
1. Build NNG and mbedTLS from source via CMake (fetched automatically)
2. Use headerkit to parse NNG's C headers and generate CFFI bindings
3. Compile the CFFI extension module
4. Install test dependencies (pytest, pytest-asyncio, pytest-trio, trio)

#### Speeding Up Rebuilds (sccache & Local Sources)

Building NNG, mbedTLS, and the CFFI extensions from scratch can take time. You can dramatically accelerate local compile times using **sccache** (compiler caching) and local source clones:

##### 1. Enable compiler caching with `sccache` (Recommended)

[`sccache`](https://github.com/mozilla/sccache) acts as a drop-in compiler wrapper for GCC, Clang, and MSVC, caching precompiled C object files so recompilations are nearly instantaneous:

- **macOS**: `brew install sccache`
- **Linux**: `sudo apt install sccache` (or `cargo install sccache`)
- **Windows**: `winget install Mozilla.sccache`

Once installed, tell CMake to use it as the compiler launcher:

```bash
export CMAKE_C_COMPILER_LAUNCHER=sccache
pip install -e '.[dev]'
```

##### 2. Cache or reuse CMake dependencies locally

By default, CMake's `FetchContent` downloads NNG and mbedTLS from GitHub during
the build. To avoid re-downloading across rebuilds or clean environments, you can point CMake to local clones:

```bash
# Clone once locally
git clone https://github.com/nanomsg/nng ~/deps/nng
git clone https://github.com/Mbed-TLS/mbedtls ~/deps/mbedtls

# Build with local sources via CMake defines
pip install -e . \
  -C cmake.define.FETCHCONTENT_SOURCE_DIR_NNG=$HOME/deps/nng \
  -C cmake.define.FETCHCONTENT_SOURCE_DIR_MBEDTLS=$HOME/deps/mbedtls
```

#### Testing Free-Threaded Python (PEP 703)

`pynng` supports free-threaded CPython (Python 3.13t and 3.14t with the GIL disabled):

```bash
uv venv --python 3.13t .venv-freethreaded
source .venv-freethreaded/bin/activate
uv pip install -e '.[dev]'
pytest test
```

### Running Tests

```bash
pytest test                         # full suite
pytest test/test_protocols.py       # specific file
pytest -x test                      # stop on first failure
pytest -k "test_pair"               # run matching tests
```

Test configuration is in `pyproject.toml` under `[tool.pytest.ini_options]`.
Tests run with `--capture=no --verbose` by default.

### Code Style

pynng uses [ruff](https://docs.astral.sh/ruff/) for linting and formatting,
configured via pre-commit hooks.

- Max line length: 88 characters
- Python target: 3.10+
- Enforced checks: trailing whitespace, end-of-file newlines, YAML/TOML validity

Run the linter manually:

```bash
pre-commit run --all-files
```

## Making Changes

1. Fork the repository
2. Create a feature branch from `master`
3. Make your changes
4. Run tests: `pytest test`
5. Run linting: `pre-commit run --all-files`
6. Submit a pull request targeting `master`

### Branch Policy

- `master` is the stable branch and will never be force-pushed.
- All other branches may be deleted, rebased, force-pushed, or otherwise modified.
- PRs should target `master` (or the appropriate development branch if one exists).

### Changelog

pynng uses [Keep a Changelog](https://keepachangelog.com/) format.
Add an entry to `CHANGELOG.md` under `## [Unreleased]` for any user-facing changes.
Categorize your entry as one of: Added, Changed, Fixed, Deprecated, Removed, Security.

## Building Documentation

```bash
pip install -e '.[docs]'
cd docs
make html
# Open _build/html/index.html in your browser
```

The docs use [Sphinx](https://www.sphinx-doc.org/) with the
[Read the Docs theme](https://sphinx-rtd-theme.readthedocs.io/) and
[sphinxcontrib-trio](https://sphinxcontrib-trio.readthedocs.io/) for async
function documentation.

## CI Workflows

| Workflow | Purpose | Trigger |
|----------|---------|---------|
| `smoketest` | Run tests on Python 3.10-3.14 (Ubuntu) | Push, PR |
| `cibuildwheel` | Build wheels for all platforms, publish releases | Push, PR, Release |
| `benchmarks` | Performance regression testing and throughput benchmarks | Push, PR |
| `check-nng` | Check for NNG upstream updates | Daily |
| `check-python` | Check for new Python versions | Weekly (Monday) |
| `pre-commit-autoupdate` | Update pre-commit hooks | Weekly (Tuesday) |

### Testing CI Locally

You can test GitHub Actions locally using the [nektos/act](https://github.com/nektos/act) tool:

```bash
# Run cibuildwheel on Linux
act --container-options='-u root' \
    -W .github/workflows/cibuildwheel.yml \
    --matrix os:ubuntu-24.04 \
    --pull=false \
    --artifact-server-path=artifacts
```

- `--pull=false` prevents downloading the latest runner docker image.
- `--artifact-server-path=artifacts` enables an artifact server so you can
  inspect the built artifacts.

## Release Process

Releases are triggered by creating a GitHub Release:

1. Tag the commit and push:

   ```bash
   git tag vx.y.z -m "Release version x.y.z."
   git push --tags
   ```

2. Create a GitHub Release for that tag. The `cibuildwheel` workflow will
   automatically build wheels for all supported platforms and publish to
   PyPI using OIDC trusted publishing.

Versioning is handled by [setuptools-scm](https://github.com/pypa/setuptools-scm),
which derives the version from git tags.

## Debugging

To get a debug build, change `cmake.build-type` from `"Release"` to `"Debug"`
in `pyproject.toml`, then reinstall:

```bash
uv pip install -v -e '.[dev]'
```

This builds all C extensions and libraries with debug symbols. You can then
debug the C code using gdb or lldb. For VS Code with lldb:

1. Set a breakpoint in the Python code before the C code you want to debug.
2. Run the Python code via the debugger (e.g., `Python: Current File` launch config).
3. When the breakpoint is hit, launch the `Attach (lldb)` configuration in VS Code
   and select the process from the list.
4. You should now be able to step through the C code when you release the Python
   breakpoint.
