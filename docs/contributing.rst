Contributing
============

See the `Contributing Guide <https://github.com/codypiersall/pynng/blob/master/CONTRIBUTING.md>`_
for full details on how to contribute to pynng.

Quick Summary
-------------

**Setup:**

.. code-block:: bash

   git clone https://github.com/codypiersall/pynng
   cd pynng
   uv pip install -e '.[dev]'
   pre-commit install

**Prerequisites:** Python 3.10+, CMake 3.26+, ninja-build, libclang
(Ubuntu: ``sudo apt install ninja-build libclang-dev``;
macOS: Xcode command line tools).

**Run tests:**

.. code-block:: bash

   pytest test

**Run linting:**

.. code-block:: bash

   pre-commit run --all-files

**Workflow:**

1. Fork the repository
2. Create a feature branch from ``master``
3. Make changes, run tests, run linting
4. Add a changelog entry to ``CHANGELOG.md`` under ``[Unreleased]``
5. Submit a pull request targeting ``master``

**Build docs:**

.. code-block:: bash

   pip install -e '.[docs]'
   cd docs
   make html

CI Workflows
------------

.. list-table::
   :header-rows: 1
   :widths: 25 40 35

   * - Workflow
     - Purpose
     - Trigger
   * - ``smoketest``
     - Run tests on Python 3.10-3.14 (Ubuntu)
     - Push, PR
   * - ``cibuildwheel``
     - Build wheels for all platforms, publish releases
     - Push, PR, Release
   * - ``check-nng``
     - Check for NNG upstream updates
     - Daily
   * - ``check-python``
     - Check for new Python versions
     - Weekly (Monday)
   * - ``pre-commit-autoupdate``
     - Update pre-commit hooks
     - Weekly (Tuesday)
