Getting Started
===============

This tutorial walks you through installing pynng and using the most common
messaging patterns. Every example below is complete and can be copied into a
file and run directly.

Installation
------------

Install pynng from PyPI::

    pip install pynng

Pre-built wheels are available for Linux, macOS, and Windows on common Python
versions. If no wheel is available for your platform, pip will build from
source (which requires a C compiler and libclang).

Your First Pair Socket
----------------------

The simplest pattern is **pair**: two sockets connected point-to-point, each
able to send and receive. One socket calls :meth:`~pynng.Socket.listen` (the
server) and the other calls :meth:`~pynng.Socket.dial` (the client).

.. code-block:: python

    from pynng import Pair0

    address = "tcp://127.0.0.1:54321"

    with Pair0(listen=address) as server, Pair0(dial=address) as client:
        client.send(b"Hello server!")
        print(server.recv())   # b'Hello server!'

        server.send(b"Hello client!")
        print(client.recv())   # b'Hello client!'

Key points:

- Data is always ``bytes``, never ``str``. If you accidentally pass a string,
  pynng raises a ``ValueError`` with a helpful message.
- Use sockets as context managers (``with``) so they are automatically closed.
- You can pass ``listen=`` or ``dial=`` directly in the constructor as a
  shortcut.

Your First Pub/Sub
------------------

The **publish/subscribe** pattern lets one publisher broadcast messages to many
subscribers. Subscribers must call :meth:`~pynng.Sub0.subscribe` to choose
which messages to receive. A subscription is a prefix match on the raw bytes
of the message.

.. code-block:: python

    import time
    from pynng import Pub0, Sub0, Timeout

    address = "tcp://127.0.0.1:54322"

    with Pub0(listen=address) as pub, \
         Sub0(dial=address, recv_timeout=500) as sub:

        # Subscribe to messages starting with "weather:"
        sub.subscribe(b"weather:")

        # Give the subscriber time to connect
        time.sleep(0.1)

        pub.send(b"weather:sunny")
        pub.send(b"sports:goal!")

        print(sub.recv())  # b'weather:sunny'

        # "sports:goal!" is silently dropped because sub is not subscribed

        try:
            sub.recv()
        except Timeout:
            print("No more matching messages")

Key points:

- Subscribe to ``b""`` (empty bytes) to receive all messages.
- A subscriber that has no subscriptions receives nothing.
- Pub/sub is a "best effort" transport; messages may be silently dropped under
  heavy load.

Your First Req/Rep
------------------

The **request/reply** pattern models a client asking a question and a server
answering it. The :class:`~pynng.Req0` socket sends a request, and the
:class:`~pynng.Rep0` socket receives it and sends back a reply.

.. code-block:: python

    from pynng import Req0, Rep0

    address = "tcp://127.0.0.1:54323"

    with Rep0(listen=address) as server, Req0(dial=address) as client:
        # Client sends a request
        client.send(b"What is 2 + 2?")

        # Server receives the request and sends a reply
        question = server.recv()
        print(f"Server got: {question}")  # b'What is 2 + 2?'
        server.send(b"4")

        # Client receives the reply
        answer = client.recv()
        print(f"Answer: {answer}")  # b'4'

Key points:

- A Req0 socket must send before it can receive (and vice versa for Rep0).
  Violating this order raises :class:`~pynng.BadState`.
- For handling multiple concurrent requests on a single socket, use
  :class:`~pynng.Context` (see :doc:`async`).

A Taste of Async
----------------

pynng supports asynchronous send and receive with both :mod:`asyncio` and
`Trio`_. Use :meth:`~pynng.Socket.asend` and :meth:`~pynng.Socket.arecv`
instead of their synchronous counterparts:

.. code-block:: python

    import asyncio
    import pynng

    async def main():
        address = "tcp://127.0.0.1:54324"
        async with pynng.Pair0(listen=address) as server:
            async with pynng.Pair0(dial=address) as client:
                await client.asend(b"Hello async!")
                msg = await server.arecv()
                print(msg)  # b'Hello async!'

    asyncio.run(main())

Sockets support ``async with`` for automatic cleanup and ``async for`` for
iterating over incoming messages. See the :doc:`async` for the full guide.

.. _Trio: https://trio.readthedocs.io

Next Steps
----------

- :doc:`protocols` -- Learn about all the messaging patterns (push/pull,
  survey, bus, and more).
- :doc:`async` -- Async patterns, cancellation, timeouts, and concurrent
  contexts.
- :doc:`transports` -- TCP, IPC, in-process, WebSocket, and abstract socket
  transports.
- :doc:`tls` -- Securing connections with TLS.
- :doc:`api/sockets` -- Full API reference for Socket and all protocol classes.
