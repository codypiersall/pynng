Architecture
============

This document describes the internal architecture of pynng for contributors
and anyone interested in understanding how the library works.

Build System
------------

pynng uses `scikit-build-core <https://scikit-build-core.readthedocs.io/>`_ as its
build backend, configured in ``pyproject.toml``. The build process:

1. **CMake fetches dependencies**: ``CMakeLists.txt`` uses ``FetchContent`` to
   download NNG and mbedTLS from GitHub (or from local clones if configured).
   NNG is built as a static library with TLS support via mbedTLS.

2. **headerkit generates CFFI declarations**: At build time,
   `headerkit <https://github.com/axiomantic/headerkit>`_ parses NNG's C
   headers using libclang and auto-generates the CFFI module definition file
   ``pynng/_nng.py``. This replaces the previously hand-maintained CFFI
   declarations.

3. **CFFI compiles the extension**: The ``_nng`` module is compiled as a CFFI
   ABI-mode extension, providing the ``lib`` and ``ffi`` objects that bridge
   Python to the NNG C library.

4. **setuptools-scm provides versioning**: The version is derived from git tags
   and written to ``pynng/_version.py``.

Code Organization
-----------------

::

    pynng/
      __init__.py       Public API re-exports
      nng.py            Core: Socket, Pipe, Context, Message, protocol classes
      _aio.py           Async layer: AIOHelper, asyncio/trio integration
      options.py        Option getter/setter functions
      tls.py            TLSConfig wrapper
      sockaddr.py       Socket address types (SockAddr, InprocAddr, IPCAddr, etc.)
      exceptions.py     Exception hierarchy mapping NNG error codes
      _nng.py           Auto-generated CFFI module definition (not in source tree)
      _version.py       Auto-generated version (setuptools-scm, not in source tree)


Key Patterns
------------

Descriptor Protocol for Options
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Socket options (``recv_timeout``, ``protocol_name``, ``tcp_nodelay``, etc.) are
implemented as Python `descriptors <https://docs.python.org/3/howto/descriptor.html>`_.
The base class ``_NNGOption`` defines ``__get__`` and ``__set__`` methods that
dispatch to type-specific getter/setter functions in ``options.py``.

Concrete descriptor subclasses set which getter/setter to use:

- ``IntOption`` -- ``_getopt_int`` / ``_setopt_int``
- ``MsOption`` -- ``_getopt_ms`` / ``_setopt_ms`` (durations in milliseconds)
- ``SizeOption`` -- ``_getopt_size`` / ``_setopt_size``
- ``StringOption`` -- ``_getopt_string`` / ``_setopt_string``
- ``BooleanOption`` -- ``_getopt_bool`` / ``_setopt_bool``
- ``SockAddrOption`` -- ``_getopt_sockaddr`` (read-only)
- ``PointerOption`` -- ``_setopt_ptr`` (write-only, used for TLS config)

This means ``sock.recv_timeout = 5000`` calls the appropriate NNG C function
(``nng_socket_set_ms``) without the user needing to know anything about the C API.

The same descriptor classes are reused across ``Socket``, ``Dialer``,
``Listener``, ``Pipe``, and ``Context``. The ``_get_inst_and_func`` helper in
``options.py`` determines which NNG function to call based on the Python
object type.

CFFI for C Bindings
^^^^^^^^^^^^^^^^^^^^

pynng uses `cffi <https://cffi.readthedocs.io/>`_ in ABI mode to call NNG
functions. The ``lib`` and ``ffi`` objects from the ``_nng`` module are the
bridge between Python and C. All interaction with NNG goes through these
objects:

- ``lib.nng_*()`` -- NNG function calls
- ``ffi.new()`` -- allocate C data structures
- ``ffi.def_extern()`` -- define callback functions callable from C

Async Layer
^^^^^^^^^^^^

``_aio.py`` wraps NNG's asynchronous I/O (``nng_aio``) with Python
async/await support. The design supports multiple async frameworks:

1. ``AIOHelper`` is created for each async operation (send or receive).
2. It uses `sniffio <https://sniffio.readthedocs.io/>`_ to detect whether
   ``asyncio`` or ``trio`` is the active event loop.
3. A framework-specific helper (``asyncio_helper`` or ``trio_helper``) creates:

   - An **awaitable** that the calling code can ``await``
   - A **rescheduler callback** that NNG's C callback will invoke to wake up
     the Python coroutine

4. NNG calls the C callback ``_async_complete`` when the async operation
   finishes. This callback looks up the rescheduler in ``_aio_map`` and
   invokes it.
5. For asyncio, the rescheduler uses ``loop.call_soon_threadsafe()`` to
   resolve a ``Future``. For trio, it uses ``trio.lowlevel.reschedule()``
   to wake the task.

Both ``Socket`` and ``Context`` support ``async with`` (async context manager)
and ``async for`` (async iteration over received messages).

Pipe Callbacks
^^^^^^^^^^^^^^^

NNG notifies Python of pipe events (connect, disconnect) via C callbacks.
The mechanism works as follows:

1. When a ``Socket`` is created, it registers ``_nng_pipe_cb`` as the callback
   for all pipe events using ``nng_pipe_notify``.
2. A ``ffi.new_handle()`` is used to pass the Python ``Socket`` object through
   the C callback safely.
3. When a pipe event fires, ``_nng_pipe_cb`` retrieves the ``Socket`` from the
   handle, creates or looks up the ``Pipe`` object, and invokes any user-registered
   callbacks.
4. Users register callbacks via ``add_pre_pipe_connect_cb``,
   ``add_post_pipe_connect_cb``, and ``add_post_pipe_remove_cb``.

A threading lock (``_pipe_notify_lock``) ensures thread-safety of pipe
bookkeeping, which is important for free-threaded Python (3.14t).

Error Handling
--------------

NNG functions return integer error codes. pynng maps these to Python exceptions:

1. ``check_err(err)`` is called after every NNG function call.
2. If the return value is non-zero, ``check_err`` looks up the error code in
   ``EXCEPTION_MAP`` and raises the corresponding exception.
3. All exceptions inherit from ``NNGException``, which carries an ``errno``
   attribute with the raw NNG error code.
4. The exception hierarchy is flat -- all exception classes directly subclass
   ``NNGException``. Common exceptions include ``Timeout``, ``Closed``,
   ``ConnectionRefused``, ``TryAgain``, and ``BadState``.
5. ``MessageStateError`` is a separate exception (inheriting from ``Exception``,
   not ``NNGException``) that indicates misuse of the ``Message`` API (e.g.,
   accessing a message buffer after it has been sent).

Class Hierarchy
---------------

Protocol Sockets
^^^^^^^^^^^^^^^^^

All protocol sockets inherit from ``Socket``:

- ``Bus0`` -- mesh networking
- ``Pair0`` -- one-to-one bidirectional
- ``Pair1`` -- bidirectional with optional polyamorous mode
- ``Push0`` / ``Pull0`` -- data pipeline
- ``Pub0`` / ``Sub0`` -- publish/subscribe (``Sub0`` adds ``subscribe``/``unsubscribe``)
- ``Req0`` / ``Rep0`` -- request/response (``Req0`` adds ``resend_time``)
- ``Surveyor0`` / ``Respondent0`` -- survey pattern (``Surveyor0`` adds ``survey_time``)

Each protocol class sets ``_opener`` to the corresponding NNG open function
(e.g., ``lib.nng_pair0_open``). The ``Socket.__init__`` calls ``self._opener``
to create the underlying NNG socket.

Supporting Classes
^^^^^^^^^^^^^^^^^^^

- ``Dialer`` -- represents a dial (outgoing connection) on a socket
- ``Listener`` -- represents a listen (incoming connection) on a socket
- ``Pipe`` -- a single connection between two endpoints
- ``Context`` -- multiplexes a socket for concurrent stateful operations
  (useful with Req0/Rep0)
- ``Message`` -- wraps ``nng_msg`` for advanced send/receive with pipe routing
- ``TLSConfig`` -- configures TLS transport settings
