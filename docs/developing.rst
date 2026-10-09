Pynng Developer Notes
=====================

A list of notes, useful only to developers of the library, and not for users.

Build System
------------

pynng uses `scikit-build-core`_ as its build backend (configured in
``pyproject.toml``). The build process:

1. CMake fetches NNG and mbedTLS via ``FetchContent``
2. `headerkit`_ parses NNG's C headers using libclang to auto-generate CFFI
   bindings (``pynng/_nng.py``)
3. CFFI compiles the extension module
4. `setuptools-scm`_ derives the version from git tags

Install for development with:

.. code-block:: bash

   uv pip install -e '.[dev]'

Testing without pulling dependencies from GitHub
-------------------------------------------------

By default, CMake's ``FetchContent`` downloads NNG and mbedTLS from GitHub during
the build. To speed up development iteration, you can point the build to local
clones instead by passing CMake defines:

.. code-block:: bash

   # Clone once locally
   git clone https://github.com/nanomsg/nng ~/deps/nng
   git clone https://github.com/Mbed-TLS/mbedtls ~/deps/mbedtls

   # Build with local sources via CMake defines
   pip install -e . \
     -C cmake.define.FETCHCONTENT_SOURCE_DIR_NNG=$HOME/deps/nng \
     -C cmake.define.FETCHCONTENT_SOURCE_DIR_MBEDTLS=$HOME/deps/mbedtls

Testing CI changes
------------------

When testing CI changes, it can be painful, embarrassing, and tedious, to push changes
just to see how CI does. Sometimes this is necessary, for example for architectures or
operating systems you do not own so cannot test on. However, you *can* test CI somewhat
using the incredible `nektos/act`_ tool. It enables running Github Actions locally. We
do need to pass some flags to make the tool do what we want.

If you have single failing tests, you can narrow down the build by setting specific
`cibuildwheel options`_ in the ``pyproject.toml`` file, to skip certain Python versions
or architectures.

Running CI Locally
##################

Use this command to run Github Actions locally using the `nektos/act`_ tool

.. code-block:: bash

   # run cibuildwheel, using ubuntu-24.04 image
   # This is how  you test on Linux
   # Needs --container-options='-u root' so cibuildwheel can launch its own docker containers
   act --container-options='-u root' \
       -W .github/workflows/cibuildwheel.yml \
       --matrix os:ubuntu-24.04 \
       --pull=false \
       --artifact-server-path=artifacts

``--pull=false`` prevents downloading the latest runner docker image.
``--artifact-server-path=artifacts`` enables an artifact server, and lets you look at
the built artifacts afterwards.

Making a new release
--------------------

We use `setuptools-scm`_ to properly version the project, and GitHub Actions to build
wheels via cibuildwheel. Publishing to PyPI uses OIDC trusted publishing.

1. Tag the commit locally, and push:

   .. code-block:: bash

       git tag vx.y.z -m "Release version x.y.z."
       git push --tags

2. Create a GitHub Release for that tag. The ``cibuildwheel`` workflow will
   automatically build wheels for all supported platforms and publish to PyPI.

.. note::

   The ``publish`` job in the ``cibuildwheel`` workflow triggers on
   ``release: [published]`` events. It uses PyPI's OIDC trusted publishing,
   so no API tokens are needed. The PyPI trusted publisher must be configured
   to trust the ``cibuildwheel.yml`` workflow in the ``pypi`` environment.

Debugging
---------

From the pynng repo directory, install it with:

.. code-block:: bash

   uv pip install -v -e '.[dev]'

To get a debug build, change ``cmake.build-type`` from ``"Release"`` to ``"Debug"``
in ``pyproject.toml``.

This will build all C extensions and libraries with debug symbols. You can then
debug the C code using gdb or lldb. The following instructions are for
VS Code and lldb:

1. Set a breakpoint in the Python code before the C code you want to debug would be called.
2. Run the Python code via debugger. You can use the `Python: Current File` launch
   configuration in VS Code or the VS Code test runner's debug mode.
3. When the breakpoint is hit, launch the ``Attach (lldb)`` configuration in VS Code and
   select the process from the list. It may not be clear which process to select, so you may
   launch concurrent debuggers for all matching processes.
4. You should now be able to step through the C code in the debugger when you release the Python
   breakpoint.

.. _cibuildwheel options: https://cibuildwheel.readthedocs.io/en/stable/options/
.. _headerkit: https://github.com/axiomantic/headerkit
.. _mbedtls: https://github.com/Mbed-TLS/mbedtls
.. _nektos/act: https://github.com/nektos/act
.. _nng: https://github.com/nanomsg/nng
.. _scikit-build-core: https://scikit-build-core.readthedocs.io/
.. _setuptools-scm: https://github.com/pypa/setuptools-scm
