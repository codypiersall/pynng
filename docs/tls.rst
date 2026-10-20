TLS Guide
=========

pynng supports TLS-encrypted connections using the ``tls+tcp://`` transport
scheme. TLS is configured through the :class:`~pynng.TLSConfig` class, which
wraps NNG's TLS configuration.

.. contents:: Topics
   :local:
   :depth: 1

Overview
--------

To use TLS with pynng:

1. Create a :class:`~pynng.TLSConfig` for the server (with its certificate
   and private key).
2. Create a :class:`~pynng.TLSConfig` for the client (with the CA
   certificate to verify the server).
3. Assign the TLS config to each socket via the ``tls_config`` attribute.
4. Use ``tls+tcp://`` as the transport scheme when listening and dialing.

Server Configuration
--------------------

The server needs its own certificate and private key. Create a
:class:`~pynng.TLSConfig` with ``MODE_SERVER``:

.. code-block:: python

    from pynng import TLSConfig

    server_tls = TLSConfig(
        TLSConfig.MODE_SERVER,
        own_cert_string=SERVER_CERT,   # PEM-encoded certificate
        own_key_string=SERVER_KEY,     # PEM-encoded private key
        server_name="localhost",
    )

You can also load the certificate and key from a combined PEM file:

.. code-block:: python

    server_tls = TLSConfig(
        TLSConfig.MODE_SERVER,
        cert_key_file="/path/to/combined.pem",  # contains both cert and key
        server_name="localhost",
    )

.. note::

   ``own_cert_string``/``own_key_string`` and ``cert_key_file`` are mutually
   exclusive. You cannot set both.

Client Configuration
--------------------

The client needs the CA certificate to verify the server's identity. Create
a :class:`~pynng.TLSConfig` with ``MODE_CLIENT``:

.. code-block:: python

    from pynng import TLSConfig

    client_tls = TLSConfig(
        TLSConfig.MODE_CLIENT,
        ca_string=CA_CERT,            # PEM-encoded CA certificate
        server_name="localhost",      # must match server certificate's CN/SAN
    )

Or load the CA certificate from a file:

.. code-block:: python

    client_tls = TLSConfig(
        TLSConfig.MODE_CLIENT,
        ca_files=["/path/to/ca.crt"],
        server_name="localhost",
    )

.. note::

   ``ca_string`` and ``ca_files`` are mutually exclusive. You cannot set
   both.

Authentication Modes
--------------------

:class:`~pynng.TLSConfig` supports three authentication modes, set via the
``auth_mode`` parameter or the :meth:`~pynng.TLSConfig.set_auth_mode`
method:

- ``TLSConfig.AUTH_MODE_REQUIRED`` -- The peer must present a valid
  certificate. This is the default for clients.
- ``TLSConfig.AUTH_MODE_OPTIONAL`` -- The peer may present a certificate;
  if it does, it must be valid.
- ``TLSConfig.AUTH_MODE_NONE`` -- No certificate verification is performed.

.. code-block:: python

    from pynng import TLSConfig

    # Skip server certificate verification (for development/testing only!)
    client_tls = TLSConfig(
        TLSConfig.MODE_CLIENT,
        auth_mode=TLSConfig.AUTH_MODE_NONE,
    )

.. warning::

   Using ``AUTH_MODE_NONE`` disables certificate verification entirely.
   Only use this for development and testing. In production, always use
   ``AUTH_MODE_REQUIRED`` with proper CA certificates.

Server Name (SNI)
-----------------

The ``server_name`` parameter sets the expected server name for TLS Server
Name Indication (SNI). For clients, this must match the Common Name (CN) or
a Subject Alternative Name (SAN) in the server's certificate:

.. code-block:: python

    client_tls = TLSConfig(
        TLSConfig.MODE_CLIENT,
        ca_string=CA_CERT,
        server_name="myservice.example.com",
    )

You can also set or change the server name after construction:

.. code-block:: python

    tls_config.set_server_name("myservice.example.com")

To clear the server name, pass an empty string:

.. code-block:: python

    tls_config.set_server_name("")

Complete Example
----------------

Here is a complete example of two sockets communicating over TLS. This
uses self-signed certificates (the CA certificate is the same as the server
certificate):

.. code-block:: python

    import socket
    from pynng import Pair0, TLSConfig

    # In a real application, these would be loaded from files.
    # See test/test_tls.py in the pynng repository for sample
    # PEM-encoded certificates.

    SERVER_CERT = "..."  # PEM-encoded server certificate
    SERVER_KEY = "..."   # PEM-encoded server private key
    CA_CERT = SERVER_CERT  # Self-signed: CA cert is the server cert

    # Configure TLS for the server
    server_tls = TLSConfig(
        TLSConfig.MODE_SERVER,
        own_cert_string=SERVER_CERT,
        own_key_string=SERVER_KEY,
        server_name="localhost",
    )

    # Configure TLS for the client
    client_tls = TLSConfig(
        TLSConfig.MODE_CLIENT,
        ca_string=CA_CERT,
        server_name="localhost",
    )

    # Create sockets and assign TLS configs
    with Pair0(recv_timeout=1000, send_timeout=1000) as server, \
         Pair0(recv_timeout=1000, send_timeout=1000) as client:

        server.tls_config = server_tls
        client.tls_config = client_tls

        # Listen on port 0 to get a random available port
        server.listen("tls+tcp://localhost:0")

        # Get the assigned port from the listener
        sa = server.listeners[0].local_address
        port = socket.ntohs(sa.port)

        # Dial the server
        client.dial(f"tls+tcp://localhost:{port}")

        # Communicate as normal
        client.send(b"Hello over TLS!")
        print(server.recv())  # b'Hello over TLS!'

        server.send(b"Secure reply")
        print(client.recv())  # b'Secure reply'

Using TLS with Files
--------------------

For production deployments, you will typically load certificates from files
rather than embedding them as strings:

.. code-block:: python

    from pynng import TLSConfig

    # Server: combined cert+key PEM file
    server_tls = TLSConfig(
        TLSConfig.MODE_SERVER,
        cert_key_file="/etc/ssl/myservice/server.pem",
        server_name="myservice.example.com",
    )

    # Client: CA certificate file
    client_tls = TLSConfig(
        TLSConfig.MODE_CLIENT,
        ca_files=["/etc/ssl/certs/ca-bundle.crt"],
        server_name="myservice.example.com",
    )

You can pass multiple CA files if your trust chain requires it:

.. code-block:: python

    client_tls = TLSConfig(
        TLSConfig.MODE_CLIENT,
        ca_files=["/path/to/root-ca.crt", "/path/to/intermediate-ca.crt"],
        server_name="myservice.example.com",
    )

Post-Construction Configuration
--------------------------------

:class:`~pynng.TLSConfig` also supports setting properties after construction
via individual methods. This can be useful for building up a configuration
step by step:

.. code-block:: python

    from pynng import TLSConfig

    config = TLSConfig(TLSConfig.MODE_CLIENT)
    config.set_server_name("myservice.example.com")
    config.set_ca_chain(ca_pem_string)
    config.set_auth_mode(TLSConfig.AUTH_MODE_REQUIRED)

Available methods:

- :meth:`~pynng.TLSConfig.set_server_name` -- Set the expected server name.
- :meth:`~pynng.TLSConfig.set_ca_chain` -- Set the CA chain from a PEM
  string. Optionally accepts a CRL string as the second argument.
- :meth:`~pynng.TLSConfig.set_own_cert` -- Set own certificate and key from
  PEM strings. Optionally accepts a password for encrypted keys.
- :meth:`~pynng.TLSConfig.set_auth_mode` -- Set the authentication mode.
- :meth:`~pynng.TLSConfig.add_ca_file` -- Add a CA certificate from a file.
- :meth:`~pynng.TLSConfig.set_cert_key_file` -- Load own certificate and
  key from a file.

See the :doc:`api/tls` reference for full API details.
