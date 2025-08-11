==========================
Pynng's core functionality
==========================

At the heart of pynng is the :class:`pynng.Socket`.  It takes no positional
arguments, and all keyword arguments are optional.  It is the Python version of
`nng_socket <https://nanomsg.github.io/nng/man/tip/nng_socket.5.html>`_.

----------
The Socket
----------

.. Note::

    You should never instantiate a :class:`pynng.Socket` directly.  Rather, you
    should instantiate one of the :ref:`subclasses <available-protocols>`.

.. autoclass:: pynng.Socket(*, listen=None, dial=None, **kwargs)
   :members: listen, dial, send, recv, asend, arecv, recv_msg, arecv_msg, new_context

Feel free to peruse the `examples online
<https://github.com/codypiersall/pynng/tree/master/examples>`_, or ask in the
`gitter channel <https://gitter.im/nanomsg/nanomsg>`_.

.. _available-protocols :

###################
Available Protocols
###################

.. autoclass:: pynng.Pair0(**kwargs)
.. autoclass:: pynng.Pair1
.. autoclass:: pynng.Req0
.. autoclass:: pynng.Rep0(**kwargs)
.. autoclass:: pynng.Pub0(**kwargs)
.. autoclass:: pynng.Sub0(**kwargs)
   :members:
.. autoclass:: pynng.Push0(**kwargs)
.. autoclass:: pynng.Pull0(**kwargs)
.. autoclass:: pynng.Surveyor0(**kwargs)
.. autoclass:: pynng.Respondent0(**kwargs)
.. autoclass:: pynng.Bus0(**kwargs)

----
Pipe
----

.. autoclass:: pynng.Pipe(...)
   :members: send, asend

-------
Context
-------

.. autoclass:: pynng.Context(...)
   :members: send, asend, recv, arecv, recv_msg, arecv_msg, close

-------
Message
-------

.. autoclass:: pynng.Message(data)

------
Dialer
------

.. autoclass:: pynng.Dialer(...)
   :members: close

--------
Listener
--------

.. autoclass:: pynng.Listener(...)
   :members: close


---------
TLSConfig
---------

Sockets can make use of the TLS transport on top of TCP by specifying an
address similar to how tcp is specified.  The following are examples of valid
TLS addresses:

* ``"tls+tcp:127.0.0.1:1313"``, listening on TCP port 1313 on localhost.
* ``"tls+tcp4:127.0.0.1:1313"``, explicitly requesting IPv4 for TCP port 1313
  on localhost.
* ``"tls+tcp6://[::1]:4433"``, explicitly requesting IPv6 for IPv6 localhost on
  port 4433.


.. autoclass:: pynng.TLSConfig(...)

-----------------
Abstract Sockets
-----------------

Abstract sockets are a Linux-specific feature that allows for socket communication
without creating files in the filesystem. They are identified by names in an
abstract namespace and are automatically freed by the system when no longer in use.

Abstract sockets use the ``abstract://`` URL scheme. For example:

* ``"abstract://my_socket"`` - a simple abstract socket name
* ``"abstract://test%00socket"`` - a socket name with a NUL byte (URI-encoded)
* ``"abstract://"`` - an empty name for auto-bind (system assigns a name)

**Important:** Abstract sockets are only available on Linux systems. Attempting to use
them on other platforms will result in an error.

Abstract sockets have the following characteristics:

* They do not have any representation in the file system
* They are automatically freed by the system when no longer in use
* They ignore socket permissions
* They support arbitrary values in the path, including embedded NUL bytes
* The name does not include the leading NUL byte used in the low-level socket address

**URI Encoding:** Abstract socket names can contain arbitrary bytes, including NUL
bytes. These are represented using URI encoding. For example, the name ``"a\0b"``
would be represented as ``"abstract://a%00b"``.

**Auto-bind:** An empty name may be used with a listener to request "auto bind"
be used to select a name. In this case, the system will allocate a free name.
The name assigned can be retrieved using the ``NNG_OPT_LOCADDR`` option.

**Example:**

.. code-block:: python

    import pynng
    import platform

    # Check if we're on Linux
    if platform.system() != "Linux":
        print("Abstract sockets are only supported on Linux")
        exit(1)

    # Create a socket with abstract address
    with pynng.Pair0() as sock:
        # Listen on an abstract socket
        listener = sock.listen("abstract://my_test_socket")

        # Get the local address
        local_addr = listener.local_address
        print(f"Address family: {local_addr.family_as_str}")
        print(f"Address name: {local_addr.name}")

        # The address can be used for dialing from another process
        # dialer = sock.dial("abstract://my_test_socket")

For a complete example, see :doc:`../examples/abstract`.
