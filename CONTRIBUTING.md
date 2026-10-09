# Contributing to pynng

Thank you for your interest in contributing to pynng! This guide will help you
get set up for development and walk you through the contribution workflow.

## Getting Started

### Prerequisites

- Python 3.10+
- CMake 3.26+
- ninja-build
- libclang (for building from source -- headerkit uses it to parse NNG's C headers)
  - Ubuntu/Debian: `sudo apt install ninja-build libclang-dev`
  - macOS: Xcode command line tools (usually sufficient)
  - RHEL/CentOS/Fedora: `sudo dnf install clang-devel` (or `yum` on older systems)
  - Alpine: `apk add clang-dev`
  - Windows: LLVM (installed automatically during CI builds)

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

#### Speeding Up Rebuilds

By default, CMake's `FetchContent` downloads NNG and mbedTLS from GitHub during
the build. To speed up development iteration, you can point the build to local
clones instead:

```bash
# Clone once locally
git clone https://github.com/nanomsg/nng ~/deps/nng
git clone https://github.com/Mbed-TLS/mbedtls ~/deps/mbedtls

# Build with local sources via CMake defines
pip install -e . \
  -C cmake.define.FETCHCONTENT_SOURCE_DIR_NNG=$HOME/deps/nng \
  -C cmake.define.FETCHCONTENT_SOURCE_DIR_MBEDTLS=$HOME/deps/mbedtls
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
