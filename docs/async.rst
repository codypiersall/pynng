Async Usage Guide
=================

Both :class:`~pynng.Socket` and :class:`~pynng.Context` support modern Python
async patterns, making it natural to use pynng in async code with either
`Trio`_ or :mod:`asyncio`.

.. contents:: Topics
   :local:
   :depth: 1

Supported Async Libraries
-------------------------

pynng supports both :mod:`asyncio` and `Trio`_. The library uses `sniffio`_
to detect which event loop is running and automatically selects the right
backend. You can also pass ``async_backend="asyncio"`` or
``async_backend="trio"`` explicitly when creating a socket::

    s = pynng.Pair0(listen=address, async_backend="asyncio")

Side-by-Side Comparison
^^^^^^^^^^^^^^^^^^^^^^^

**asyncio:**

.. code-block:: python

    import asyncio
    import pynng

    async def main():
        address = "tcp://127.0.0.1:54330"
        async with pynng.Pair0(listen=address) as s0:
            async with pynng.Pair0(dial=address) as s1:
                await s0.asend(b"hello from asyncio")
                print(await s1.arecv())

    asyncio.run(main())

**Trio:**

.. code-block:: python

    import trio
    import pynng

    async def main():
        address = "tcp://127.0.0.1:54330"
        async with pynng.Pair0(listen=address) as s0:
            async with pynng.Pair0(dial=address) as s1:
                await s0.asend(b"hello from trio")
                print(await s1.arecv())

    trio.run(main)

The only differences are the import and the ``run`` call at the bottom. All
pynng async APIs are identical between the two backends.

.. _sniffio: https://github.com/python-trio/sniffio

Async Context Manager (``async with``)
---------------------------------------

Sockets and Contexts can be used as async context managers, mirroring the
synchronous ``with`` statement. The socket or context is automatically closed
when the block exits:

.. literalinclude:: snippets/async_with_example.py
   :language: python

This is equivalent to the synchronous ``with pynng.Pair0(...) as s:`` pattern,
but suitable for use inside ``async def`` functions.

Async Iteration (``async for``)
-------------------------------

Sockets and Contexts support async iteration, enabling a clean loop over
incoming messages. Internally, each iteration calls :meth:`~pynng.Socket.arecv`
and stops when the socket is closed (by catching :class:`~pynng.Closed` and
raising ``StopAsyncIteration``):

Using Trio:

.. literalinclude:: snippets/async_for_example.py
   :language: python

Using asyncio:

.. literalinclude:: snippets/async_for_asyncio_example.py
   :language: python

.. note::

   When the socket is closed, the ``async for`` loop exits cleanly via
   ``StopAsyncIteration``. Other exceptions such as ``Timeout`` propagate
   normally.

Async Close (``aclose()``)
--------------------------

Both :class:`~pynng.Socket` and :class:`~pynng.Context` provide an
:meth:`~pynng.Socket.aclose` method for consistency with Python's async
resource management conventions (e.g., ``aclose()`` on async generators).
It delegates to the synchronous :meth:`~pynng.Socket.close` since the
underlying NNG close operation is non-blocking.

Cancellation Handling
---------------------

pynng integrates with the cancellation mechanisms of both asyncio and Trio.
When an async receive or send operation is cancelled, pynng calls
``nng_aio_cancel`` on the underlying NNG async I/O object to cleanly abort
the operation.

**asyncio cancellation:**

.. code-block:: python

    import asyncio
    import pynng

    async def main():
        address = "tcp://127.0.0.1:54331"
        async with pynng.Pair0(listen=address) as s:
            # Create a task that will block on recv
            recv_task = asyncio.create_task(s.arecv())

            # Cancel after a short wait
            await asyncio.sleep(0.1)
            recv_task.cancel()

            try:
                await recv_task
            except asyncio.CancelledError:
                print("Receive was cancelled cleanly")

    asyncio.run(main())

**Trio cancellation:**

.. code-block:: python

    import trio
    import pynng

    async def main():
        address = "tcp://127.0.0.1:54331"
        async with pynng.Pair0(listen=address) as s:
            with trio.move_on_after(0.1):
                msg = await s.arecv()
                print(msg)
            print("Moved on after timeout")

    trio.run(main)

In both cases, the underlying NNG async operation is properly cancelled and
resources are freed. You do not need to worry about leaked NNG handles.

Timeout Patterns
----------------

There are two approaches to timeouts with async pynng:

**1. Socket-level timeout (``recv_timeout`` / ``send_timeout``):**

Set a timeout on the socket itself. If the operation does not complete within
this time, :class:`~pynng.Timeout` is raised:

.. code-block:: python

    import asyncio
    import pynng

    async def main():
        address = "tcp://127.0.0.1:54332"
        async with pynng.Pair0(listen=address, recv_timeout=1000) as s:
            try:
                msg = await s.arecv()
            except pynng.Timeout:
                print("No message within 1 second")

    asyncio.run(main())

**2. Event-loop-level timeout:**

Use your event loop's native timeout mechanism. This approach cancels the
operation via the event loop rather than NNG:

.. code-block:: python

    # asyncio
    import asyncio
    import pynng

    async def main():
        address = "tcp://127.0.0.1:54332"
        async with pynng.Pair0(listen=address) as s:
            try:
                msg = await asyncio.wait_for(s.arecv(), timeout=1.0)
            except asyncio.TimeoutError:
                print("No message within 1 second")

    asyncio.run(main())

.. code-block:: python

    # Trio
    import trio
    import pynng

    async def main():
        address = "tcp://127.0.0.1:54332"
        async with pynng.Pair0(listen=address) as s:
            with trio.fail_after(1.0):
                msg = await s.arecv()

    trio.run(main)

**Which to choose?** The socket-level ``recv_timeout`` works the same way in
both sync and async code and raises a pynng-specific exception. The
event-loop-level approach is more idiomatic for async code and integrates
with structured concurrency patterns (like Trio's cancel scopes). Both are
valid; use whichever fits your code style.

Concurrent Contexts
-------------------

A plain :class:`~pynng.Req0` or :class:`~pynng.Rep0` socket can only handle
one request at a time. To multiplex multiple requests over a single socket,
use :class:`~pynng.Context`.

Here is an async example of a server handling multiple concurrent requests:

.. code-block:: python

    import asyncio
    import pynng

    async def handle_request(rep_socket):
        """Handle a single request using a context."""
        ctx = rep_socket.new_context()
        try:
            data = await ctx.arecv()
            # Simulate some async work
            await asyncio.sleep(0.1)
            await ctx.asend(b"reply to: " + data)
        finally:
            ctx.close()

    async def send_request(req_socket, message):
        """Send a single request using a context."""
        ctx = req_socket.new_context()
        try:
            await ctx.asend(message)
            reply = await ctx.arecv()
            print(f"Got reply: {reply}")
        finally:
            ctx.close()

    async def main():
        address = "tcp://127.0.0.1:54333"

        async with pynng.Rep0(listen=address) as rep, \
                   pynng.Req0(dial=address) as req:

            # Launch multiple requests concurrently
            send_tasks = [
                asyncio.create_task(send_request(req, f"request {i}".encode()))
                for i in range(3)
            ]

            # Handle them on the server side
            handle_tasks = [
                asyncio.create_task(handle_request(rep))
                for _ in range(3)
            ]

            await asyncio.gather(*send_tasks, *handle_tasks)

    asyncio.run(main())

Each :class:`~pynng.Context` maintains its own protocol state, so multiple
contexts on the same socket can independently send and receive without
interfering with each other.

**Important notes about Context:**

- Contexts support the same ``async with``, ``async for``, and ``aclose()``
  patterns as sockets.
- Only :class:`~pynng.Req0` and :class:`~pynng.Rep0` support contexts.
  Other protocols raise an error when you call ``new_context()``.
- Always close contexts when you are done with them, either explicitly or
  via a context manager.

.. _Trio: https://trio.readthedocs.io
