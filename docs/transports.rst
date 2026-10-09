Transport Guide
===============

NNG supports several transports for connecting sockets. The transport is
selected by the URL scheme passed to :meth:`~pynng.Socket.listen` and
:meth:`~pynng.Socket.dial`. This guide covers all available transports, their
address formats, and when to use each one.

.. contents:: Transports
   :local:
   :depth: 1

TCP (``tcp://``)
----------------

**Address format:** ``tcp://host:port``

TCP is the default transport for communication over a network. It works on
all platforms and is the most commonly used transport.

**Examples:**

.. code-block:: python

    import pynng

    # Listen on a specific interface and port
    with pynng.Pair0(listen="tcp://127.0.0.1:5555") as s:
        pass

    # Listen on all interfaces
    with pynng.Pair0(listen="tcp://0.0.0.0:5555") as s:
        pass

    # Listen on a random available port (port 0)
    with pynng.Pair0() as s:
        s.listen("tcp://127.0.0.1:0")
        # Retrieve the assigned port from the listener's local address
        listener = s.listeners[0]
        sa = listener.local_address
        import socket
        port = socket.ntohs(sa.port)
        print(f"Listening on port {port}")

**Platform notes:**

- Works on Linux, macOS, and Windows.
- IPv6 addresses are supported using bracket notation:
  ``tcp://[::1]:5555``.

**Socket options relevant to TCP:**

- ``tcp_nodelay`` (bool): Disable Nagle's algorithm for lower latency.
  Default is ``False``.
- ``tcp_keepalive`` (bool): Enable TCP keepalive probes. Default is
  ``False``.

**Performance:** TCP adds the overhead of the TCP/IP stack (connection
setup, flow control, Nagle's algorithm). For same-machine communication,
consider IPC or inproc instead.

IPC (``ipc://``)
----------------

**Address format:** ``ipc:///path/to/socket``

IPC uses Unix domain sockets (on Linux/macOS) or named pipes (on Windows)
for communication between processes on the same machine.

**Examples:**

.. code-block:: python

    import pynng

    # Unix domain socket (Linux/macOS)
    with pynng.Pair0(listen="ipc:///tmp/my_app.sock") as server, \
         pynng.Pair0(dial="ipc:///tmp/my_app.sock") as client:
        client.send(b"hello via IPC")
        print(server.recv())

    # Windows named pipe
    # with pynng.Pair0(listen="ipc:///my_pipe") as server:
    #     ...

**When to use:** Same-machine inter-process communication where you want
lower latency than TCP without the overhead of the TCP/IP stack.

**Platform notes:**

- On Linux and macOS, this creates a Unix domain socket file at the
  specified path. Make sure the path is writable and not already in use.
- On Windows, this uses named pipes. The path format is different from
  Unix.
- The socket file is not automatically cleaned up on Linux/macOS. If the
  file already exists from a previous run, ``listen()`` may fail with
  :class:`~pynng.AddressInUse`.

**Performance:** Faster than TCP for same-machine communication because it
bypasses the TCP/IP stack entirely.

In-Process (``inproc://``)
--------------------------

**Address format:** ``inproc://arbitrary-name``

The inproc transport is for communication between threads within the same
process. The name is arbitrary and does not correspond to any filesystem
path or network address.

**Examples:**

.. code-block:: python

    import threading
    import pynng

    def worker(address):
        with pynng.Pair0(dial=address) as s:
            s.send(b"hello from worker thread")

    address = "inproc://my-pipeline"
    with pynng.Pair0(listen=address) as s:
        t = threading.Thread(target=worker, args=(address,))
        t.start()
        print(s.recv())  # b'hello from worker thread'
        t.join()

**When to use:** Inter-thread communication within a single process.
Particularly useful for building internal processing pipelines.

**Platform notes:**

- Works on all platforms.
- The name is process-scoped and exists only in memory. No filesystem or
  network resources are created.
- The listener must be created before any dialers attempt to connect (unlike
  TCP, where the dialer will retry).

**Performance:** The fastest transport. No serialization, no copying (data
is passed by reference internally), and no system calls for the data
transfer itself.

WebSocket (``ws://``, ``wss://``)
---------------------------------

**Address format:** ``ws://host:port/path`` or ``wss://host:port/path``

The WebSocket transport allows NNG sockets to communicate over WebSockets.
The ``wss://`` scheme uses TLS-encrypted WebSockets (see :doc:`tls`).

**Examples:**

.. code-block:: python

    import pynng

    # Plain WebSocket
    with pynng.Pair0(listen="ws://127.0.0.1:8080/api") as server, \
         pynng.Pair0(dial="ws://127.0.0.1:8080/api") as client:
        client.send(b"hello via WebSocket")
        print(server.recv())

**When to use:**

- Communication with browser-based clients (using a JavaScript WebSocket
  client).
- Traversing firewalls and proxies that allow HTTP/WebSocket traffic but
  block raw TCP.

**Platform notes:**

- Works on all platforms.
- The path component (``/api`` in the example) must match between listener
  and dialer.
- For TLS-encrypted WebSockets (``wss://``), configure TLS as described in
  :doc:`tls`.

**Performance:** Slightly more overhead than raw TCP due to the WebSocket
framing layer, but comparable for most workloads.

Abstract Sockets (``abstract://``)
----------------------------------

**Address format:** ``abstract://name``

Abstract sockets are a Linux-specific feature that creates a Unix domain
socket in the abstract namespace. Unlike regular IPC sockets, abstract
sockets do not create a filesystem entry and are automatically cleaned up
when no process has the socket open.

**Examples:**

.. code-block:: python

    import pynng

    # Linux only
    with pynng.Pair0(listen="abstract://my-service") as server, \
         pynng.Pair0(dial="abstract://my-service") as client:
        client.send(b"hello via abstract socket")
        print(server.recv())

**When to use:** Same-machine IPC on Linux where you want the simplicity of
IPC without managing socket files on the filesystem.

**Platform notes:**

- **Linux only.** This transport is not available on macOS or Windows.
- No filesystem entry is created, so there is no risk of stale socket files.
- The name lives in a separate namespace from filesystem paths, so
  ``abstract://foo`` and ``ipc:///foo`` are unrelated.

**Performance:** Same as IPC (Unix domain sockets under the hood).

Transport Comparison
--------------------

.. list-table::
   :header-rows: 1
   :widths: 15 20 15 50

   * - Transport
     - Scheme
     - Platforms
     - Best For
   * - TCP
     - ``tcp://``
     - All
     - Network communication, general purpose
   * - IPC
     - ``ipc://``
     - All
     - Same-machine inter-process, lower latency than TCP
   * - In-process
     - ``inproc://``
     - All
     - Inter-thread within one process, highest throughput
   * - WebSocket
     - ``ws://``, ``wss://``
     - All
     - Browser interop, firewall traversal
   * - Abstract
     - ``abstract://``
     - Linux
     - Same-machine IPC without filesystem socket files
