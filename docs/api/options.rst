Options
=======

pynng uses Python descriptors to expose NNG socket options as attributes on
:class:`~pynng.Socket`, :class:`~pynng.Context`, :class:`~pynng.Dialer`,
:class:`~pynng.Listener`, and :class:`~pynng.Pipe` objects. You interact
with options as regular Python attributes rather than calling low-level C
getter/setter functions directly.

For example::

   with pynng.Pair0(listen="tcp://127.0.0.1:5555") as sock:
       # Get the receive timeout (milliseconds)
       timeout = sock.recv_timeout

       # Set the receive timeout
       sock.recv_timeout = 1000

Options Reference Table
-----------------------

The tables below list all socket and endpoint options available in pynng, their
Python types, access mode (read/write or read-only), and which objects support them.

General Socket Options
^^^^^^^^^^^^^^^^^^^^^^

.. list-table::
   :header-rows: 1
   :widths: 22 15 12 51

   * - Option
     - Type
     - Access
     - Description
   * - ``name``
     - ``str``
     - R/W
     - Socket name for logging and debugging (``NNG_OPT_SOCKNAME``).
   * - ``raw``
     - ``bool``
     - Read-only
     - True if opened in raw (SP) mode rather than cooked mode.
   * - ``protocol``
     - ``int``
     - Read-only
     - 16-bit protocol identifier.
   * - ``protocol_name``
     - ``str``
     - Read-only
     - Human-readable protocol name (e.g. ``"pair"``, ``"sub"``).
   * - ``peer``
     - ``int``
     - Read-only
     - 16-bit peer protocol identifier.
   * - ``peer_name``
     - ``str``
     - Read-only
     - Human-readable peer protocol name.
   * - ``recv_buffer_size``
     - ``int``
     - R/W
     - Capacity of the socket receive queue in messages.
   * - ``send_buffer_size``
     - ``int``
     - R/W
     - Capacity of the socket send queue in messages.
   * - ``recv_timeout``
     - ``int`` (ms)
     - R/W
     - Receive timeout in milliseconds. Supported on Socket and Context.
   * - ``send_timeout``
     - ``int`` (ms)
     - R/W
     - Send timeout in milliseconds. Supported on Socket and Context.
   * - ``ttl_max``
     - ``int``
     - R/W
     - Maximum time-to-live / forward hops for messages.
   * - ``recv_max_size``
     - ``int`` (bytes)
     - R/W
     - Maximum message size accepted by receive operations.
   * - ``reconnect_time_min``
     - ``int`` (ms)
     - R/W
     - Minimum reconnect backoff time in milliseconds.
   * - ``reconnect_time_max``
     - ``int`` (ms)
     - R/W
     - Maximum reconnect backoff time in milliseconds.
   * - ``recv_fd``
     - ``int``
     - Read-only
     - File descriptor suitable for polling receive readiness.
   * - ``send_fd``
     - ``int``
     - Read-only
     - File descriptor suitable for polling send readiness.
   * - ``tcp_nodelay``
     - ``bool``
     - R/W
     - When True, disables Nagle's algorithm for lower latency.
   * - ``tcp_keepalive``
     - ``bool``
     - R/W
     - When True, enables TCP keepalive probes.
   * - ``tls_config``
     - ``TLSConfig``
     - Write-only
     - Assigns a :class:`~pynng.TLSConfig` object to the endpoint.

Protocol-Specific Options
^^^^^^^^^^^^^^^^^^^^^^^^^

.. list-table::
   :header-rows: 1
   :widths: 22 15 18 45

   * - Option
     - Type
     - Socket Class
     - Description
   * - ``polyamorous``
     - ``bool``
     - :class:`~pynng.Pair1`
     - When True, enables multi-peer polyamorous mode. Must be set at construction.
   * - ``resend_time``
     - ``int`` (ms)
     - :class:`~pynng.Req0`
     - Duration in milliseconds before an unacknowledged request is resent.
   * - ``survey_time``
     - ``int`` (ms)
     - :class:`~pynng.Surveyor0`
     - Window duration in milliseconds during which responses are accepted.

Dialer, Listener, and Pipe Options
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. list-table::
   :header-rows: 1
   :widths: 22 15 12 51

   * - Option
     - Type
     - Access
     - Description
   * - ``local_address``
     - ``SockAddr``
     - Read-only
     - Local :class:`~pynng.sockaddr.SockAddr` of the connection or endpoint.
   * - ``remote_address``
     - ``SockAddr``
     - Read-only
     - Remote :class:`~pynng.sockaddr.SockAddr` of the connected peer.
   * - ``url``
     - ``str``
     - Read-only
     - Configured dialer, listener, or pipe URL.
