Migration from 0.x to 1.0
==========================

This guide covers the changes between pynng 0.x and 1.0, including new
features, breaking changes, and what you need to update in your code.

.. contents:: Topics
   :local:
   :depth: 1

Build System
------------

The build system has been completely replaced. This does **not** affect
users who install via ``pip install pynng`` (pre-built wheels are available
as before), but it matters if you build from source.

**What changed:**

- **Before (0.x):** setuptools with a custom CMake build step. CFFI
  bindings were handwritten.
- **Now (1.0):** `scikit-build-core`_ with `headerkit`_ for automatic C
  header generation. CFFI bindings are auto-generated from NNG headers.

**Impact on users:**

- ``pip install pynng`` works exactly as before. No changes needed.
- Building from source now requires ``libclang`` to be available for
  headerkit's C header parsing. Install it via your system package manager
  (e.g., ``apt install libclang-dev`` on Debian/Ubuntu, ``brew install
  llvm`` on macOS).

.. _scikit-build-core: https://scikit-build-core.readthedocs.io
.. _headerkit: https://github.com/axiomantic/headerkit

Async Ergonomics (New)
----------------------

pynng 1.0 adds first-class async support patterns that were not available in
0.x.

``async with`` (Context Manager)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Sockets and contexts can now be used as async context managers:

.. code-block:: python

    # New in 1.0
    async with pynng.Pair0(listen=address) as s:
        await s.asend(b"hello")

    # 0.x equivalent (still works)
    with pynng.Pair0(listen=address) as s:
        await s.asend(b"hello")

The synchronous ``with`` statement still works in async code, but ``async
with`` is now the preferred pattern.

``async for`` (Message Iteration)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Iterate over incoming messages with a clean loop:

.. code-block:: python

    # New in 1.0
    async for msg in socket:
        print(msg)
    # Loop exits cleanly when socket is closed

Previously, you had to write your own loop with ``arecv()`` and catch
:class:`~pynng.Closed` manually.

``aclose()``
^^^^^^^^^^^^

Explicit async close for consistency with Python's async resource management
conventions:

.. code-block:: python

    await socket.aclose()

This delegates to the synchronous ``close()`` since NNG's close is
non-blocking, but having ``aclose()`` available makes pynng compatible with
protocols that expect async cleanup (e.g., ``aclose()`` on async generators).

Safety Improvements
-------------------

Several bug fixes improve safety and error handling:

**Proper error checking in option setters:**

In 0.x, ``_setopt_size`` and ``_setopt_ms`` silently ignored errors from the
NNG C library. In 1.0, these now call ``check_err()`` and raise
:class:`~pynng.NNGException` on failure. If you were relying on setting
invalid option values silently, your code will now raise exceptions.

**Better error messages:**

- ``Message._buffer`` now raises :class:`~pynng.MessageStateError` after a
  message has been sent, instead of returning ``None`` (which caused
  confusing ``TypeError`` in downstream code).
- The error message for write-only options now correctly says "is write-only"
  instead of the misleading "cannot be set."

**Thread-safe pipes property:**

The :attr:`Socket.pipes <pynng.Socket.pipes>` property is now protected by a
lock, making it safe to access from multiple threads, including
free-threaded Python 3.14t.

**Interpreter shutdown guards:**

``__del__`` methods on :class:`~pynng.Socket`, :class:`~pynng.Context`, and
:class:`~pynng.TLSConfig` now catch exceptions during interpreter shutdown,
preventing tracebacks during process exit.

**TLSConfig fixes:**

- ``AUTH_MODE_NONE`` (value 0) is now correctly applied in the constructor.
  In 0.x, the falsy value ``0`` caused the ``if auth_mode:`` check to skip
  it.
- ``set_server_name(None)`` now raises a clear ``ValueError`` instead of
  passing ``None`` to the C library.

Breaking Changes
----------------

Most pynng 0.x code will work without changes in 1.0. The following changes
may require updates:

**Option setter errors are no longer silent:**

If your code set options to invalid values and relied on the error being
silently swallowed, it will now raise :class:`~pynng.NNGException`. Fix by
ensuring option values are valid.

**Message buffer access after send:**

Accessing ``Message._buffer`` after a message has been sent now raises
:class:`~pynng.MessageStateError` instead of returning ``None``. If your
code was checking for ``None`` as a sentinel, update it to catch
``MessageStateError`` instead (or avoid accessing the message after sending).

New Features Summary
--------------------

- ``async with`` support for :class:`~pynng.Socket` and
  :class:`~pynng.Context`
- ``async for`` iteration over received messages
- ``aclose()`` method for async resource cleanup
- Abstract socket transport (``abstract://``) for Linux
- Improved TLS configuration with proper ``AUTH_MODE_NONE`` handling
- Better error messages throughout
- Thread-safe :attr:`~pynng.Socket.pipes` property
- CI improvements: concurrency groups, expanded platform testing

Upgrade Checklist
-----------------

1. **Install:** ``pip install pynng>=1.0`` works as before.
2. **Test your code:** Run your test suite. Most code will work without
   changes.
3. **Check for silent option errors:** If you see new
   :class:`~pynng.NNGException` during option setting, fix the invalid
   values.
4. **Check for Message access after send:** If you see
   :class:`~pynng.MessageStateError`, stop accessing message data after
   sending.
5. **Optional improvements:** Consider adopting ``async with``, ``async for``,
   and ``aclose()`` for cleaner async code.
6. **Building from source:** If you build from source, install ``libclang``
   for the new build system.
