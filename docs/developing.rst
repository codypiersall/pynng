Pynng Developer Notes
=====================

A list of notes, useful only to developers of the library, and not for users.

Testing without pulling dependencies from GitHub
------------------------------------------------

It can lower feedback speed dramatically when testing pynng, and needing to clone
`nng`_ and `mbedtls`_ from GitHub. If you are just doing this
one time, it is not terrible, but when you're working on *how pynng is built* it is
tedious and painful to wait for a slow internet connection.  This can be mitigated by
cloning nng and mbedtls outside of this repository, running a git server, and pointing
the ``setup.cfg`` script to

.. code-block:: bash

   # clone *once* locally
   git clone https://github.com/nanomsg/nng ~/pynng-deps/nanomsg/nng
   git clone https://github.com/Mbed-TLS/mbedtls ~/pynng-deps/Mbed-TLS/mbedtls
   # start a git daemon in the parent directory
   git daemon --reuseaddr --base-path="$HOME/pynng-deps" --export-all

Then change the ``setup.cfg`` to point to the local git server. Change the ``repo``
lines from ``repo=https://github.com/nanomsg/nng`` to
``repo=git://127.0.0.1:/nanomsg/nng``. The relevant sections of the file will look like
this:

.. code-block:: cfg

   [build_nng]
   repo=git://127.0.0.1:/nanomsg/nng

   [build_mbedtls]
   repo=git://127.0.0.1:/Mbed-TLS/mbedtls

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

   # run cibuildwheel, using ubuntu-20.04 image
   # This is how  you test on Linux
   # Needs --container-options='-u root' so cibuildwheel can launch its own docker containers
   act --container-options='-u root' \
       -W .github/workflows/cibuildwheel.yml \
       --matrix os:ubuntu-20.04 \
       --pull=false \
       --artifact-server-path=artifacts

``--pull=false`` prevents downloading the latest runner docker image.
``--artifact-server-path=artifacts`` enables an artifact server, and lets you look at
the built artifacts afterwards.

Making a new release
--------------------

We use setuptools_scm to properly version the project, and GitHub Actions to build
wheels.

1. Tag the commit locally, and push

   .. code-block:: bash

       git tag vx.y.z -m "Release version x.y.z."
       git push --tags

2. Navigate to the job through GitHub
3. Download the artifacts, and unzip them all to a directory ``pynng-x.y.z``
4. Use twine to push all the artifacts

   .. code-block:: bash

       twine upload -r pypi pynng-x.y.z/*

.. _cibuildwheel options: https://cibuildwheel.readthedocs.io/en/stable/options/
.. _mbedtls: https://github.com/Mbed-TLS/mbedtls
.. _nektos/act: https://github.com/nektos/act
.. _nng: https://github.com/nanomsg/nng

