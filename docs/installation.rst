Installation
============

From PyPI
---------

.. code-block:: bash

   pip install pynng

From source (development)
-------------------------

.. code-block:: bash

   git clone https://github.com/codypiersall/pynng
   cd pynng
   uv pip install -e '.[dev]'

Build Requirements
------------------

pynng uses `scikit-build-core <https://scikit-build-core.readthedocs.io>`_ and
`headerkit <https://github.com/axiomantic/headerkit>`_ for building. The build
process parses NNG C headers to auto-generate CFFI bindings, which requires
``libclang`` at build time.

On Ubuntu/Debian:

.. code-block:: bash

   sudo apt install ninja-build libclang-dev

On macOS, Xcode's bundled ``libclang`` is usually sufficient. If you encounter
issues with ``llvm-ranlib``, see the troubleshooting section below.

On Windows, the build process installs LLVM automatically via Chocolatey during
CI. For local builds, install LLVM from https://releases.llvm.org/.

Customizing the build
---------------------

``pynng`` 1.x builds and bundles both **NNG v1** (used by top-level ``import pynng``)
and **NNG v2** (used by ``import pynng.v2``; ``pynng`` 2.0 will make NNG v2 the
top-level default).

pynng uses CMake cache variables to configure which versions of NNG (v1 and v2)
and TLS libraries are fetched and built. You can override these at install time
using `scikit-build-core config-settings <https://scikit-build-core.readthedocs.io/en/stable/configuration/>`_:

.. code-block:: bash

   # Build against a specific NNG v1 or v2 version
   pip install -Ccmake.define.NNG_REV=v1.12.5 -Ccmake.define.NNG_V2_REV=v2.1.0 .

   # Automatically resolve NNG_REV and NNG_V2_REV to the latest upstream patch
   # release in their major.minor series (e.g. latest v1.12.x and v2.1.x)
   pip install -Ccmake.define.PYNNG_USE_LATEST_PATCH=ON .

   # Build against a fork or custom repository
   pip install -Ccmake.define.NNG_REPO=https://github.com/myorg/nng .

   # Select the TLS engine (mbed, wolf, openssl, or none)
   pip install -Ccmake.define.PYNNG_TLS_ENGINE=wolf .

   # Override mbedTLS or wolfSSL version
   pip install -Ccmake.define.MBEDTLS_REV=v3.6.5 .
   pip install -Ccmake.define.PYNNG_TLS_ENGINE=wolf -Ccmake.define.WOLFSSL_REV=v5.9.4-stable .

   # Build against system OpenSSL 3.5+ (v2 only; v1 built without TLS)
   pip install -Ccmake.define.PYNNG_TLS_ENGINE=openssl -Ccmake.define.OPENSSL_ROOT_DIR=/opt/openssl .

   # Build a Debug configuration
   pip install -Ccmake.build-type=Debug .

Available options:

.. list-table::
   :header-rows: 1
   :widths: 25 15 60

   * - Variable
     - Default
     - Description
   * - ``NNG_REPO``
     - ``https://github.com/nanomsg/nng``
     - Git URL of the NNG v1 repository to build from
   * - ``NNG_REV``
     - ``v1.12.5``
     - Git tag, branch, or commit of NNG v1 to use (``import pynng``)
   * - ``NNG_V2_REPO``
     - ``https://github.com/nanomsg/nng``
     - Git URL (or local filesystem path) of the NNG v2 repository to build from
   * - ``NNG_V2_REV``
     - ``v2.1.0``
     - Git tag, branch, or commit of NNG v2 to use (``import pynng.v2``)
   * - ``BUILD_NNG_V2``
     - ``ON``
     - Whether to build the NNG v2 extension module (``pynng._nng_v2``) alongside v1
   * - ``PYNNG_USE_LATEST_PATCH``
     - ``OFF``
     - Resolve ``NNG_REV`` and ``NNG_V2_REV`` to the latest upstream patch tag in their ``major.minor`` series
   * - ``PYNNG_TLS_ENGINE``
     - ``mbed``
     - TLS backend to build NNG against: ``mbed`` (fetches mbedTLS for v1 & v2), ``wolf`` (fetches wolfSSL with TLS 1.3 and DTLS 1.2/1.3 for v1 & v2), ``openssl`` (uses system OpenSSL 3.5+ for v2 only; v1 built without TLS), or ``none`` (disables TLS)
   * - ``MBEDTLS_REPO``
     - ``https://github.com/ARMmbed/mbedtls.git``
     - Git URL of the mbedTLS repository (when ``PYNNG_TLS_ENGINE=mbed``)
   * - ``MBEDTLS_REV``
     - ``v3.6.5``
     - Git tag, branch, or commit of mbedTLS to use
   * - ``WOLFSSL_REPO``
     - ``https://github.com/wolfSSL/wolfssl``
     - Git URL of the wolfSSL repository (when ``PYNNG_TLS_ENGINE=wolf``)
   * - ``WOLFSSL_REV``
     - ``v5.9.4-stable``
     - Git tag, branch, or commit of wolfSSL to use (configured with TLS 1.3 and DTLS 1.2/1.3 support)
   * - ``OPENSSL_ROOT_DIR``
     - *(unset)*
     - Optional root path to a system OpenSSL 3.5+ installation (when ``PYNNG_TLS_ENGINE=openssl``)
   * - ``CMAKE_BUILD_TYPE``
     - ``Release``
     - CMake build configuration (``Release`` or ``Debug``; can also be set via ``-Ccmake.build-type=Debug``)
   * - ``FETCHCONTENT_SOURCE_DIR_NNG``
     - *(unset)*
     - Point NNG v1 ``FetchContent`` to an existing local checkout instead of cloning from ``NNG_REPO``
   * - ``FETCHCONTENT_SOURCE_DIR_MBEDTLS``
     - *(unset)*
     - Point mbedTLS ``FetchContent`` to an existing local checkout instead of cloning from ``MBEDTLS_REPO``
   * - ``FETCHCONTENT_SOURCE_DIR_WOLFSSL``
     - *(unset)*
     - Point wolfSSL ``FetchContent`` to an existing local checkout instead of cloning from ``WOLFSSL_REPO``

Multiple options can be combined:

.. code-block:: bash

   pip install \
     -Ccmake.define.NNG_REPO=https://github.com/myorg/nng \
     -Ccmake.define.NNG_REV=my-branch \
     .

Troubleshooting
---------------

macOS: ``llvm-ranlib`` error
^^^^^^^^^^^^^^^^^^^^^^^^^^^^

If the build fails with an error related to ``llvm-ranlib``, you may need to
install LLVM via Homebrew and configure your path:

.. code-block:: bash

   brew install llvm
   export PATH="/opt/homebrew/opt/llvm/bin:$PATH"

Linux: ``libclang`` not found
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

If headerkit cannot find ``libclang``:

.. code-block:: bash

   sudo apt install libclang-dev
   # or install the headerkit helper:
   python -m headerkit.install_libclang
