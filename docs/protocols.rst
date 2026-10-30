Protocol Patterns
=================

pynng supports all of the scalability protocols provided by NNG. Each
protocol defines the rules for how sockets communicate. This guide covers
every protocol with examples, key options, and common pitfalls.

For full API details, see the :doc:`api/sockets` reference.

.. contents:: Protocols
   :local:
   :depth: 1

Pair (Point-to-Point)
---------------------

**When to use:** Simple bidirectional communication between exactly two peers.

Pair0
^^^^^

:class:`~pynng.Pair0` connects two sockets for one-to-one, bidirectional
communication. Each side can send and receive.

.. literalinclude:: /snippets/pair0_sync.py
   :language: python

Pair0 is the simplest protocol and a good starting point. It does not support
connecting more than two sockets; if a third peer dials, the behavior is
undefined.

Pair1
^^^^^

:class:`~pynng.Pair1` is similar to Pair0 but optionally supports connecting
to multiple peers when ``polyamorous=True`` is set at construction time.

.. warning::

   Polyamorous mode is a deprecated experimental feature in NNG and may be
   removed in a future release. See the
   `NNG docs <https://nng.nanomsg.org/man/v1.3.2/nng_pair_open.3.html>`_
   for details.

In polyamorous mode, you must use :meth:`~pynng.Socket.recv_msg` (which
returns a :class:`~pynng.Message` with a :attr:`~pynng.Message.pipe`
attribute) and :meth:`~pynng.Pipe.send` (to reply to a specific peer):

.. literalinclude:: /snippets/pair1_sync.py
   :language: python

**Key options:**

- ``polyamorous`` (bool): Must be set to ``True`` in the constructor to
  enable multi-peer mode. This is a read-only attribute after creation.

**Gotchas:**

- You must pass ``polyamorous=True`` when creating the socket; it cannot be
  changed after construction.
- Without polyamorous mode, Pair1 behaves like Pair0 (one peer only).

Pub/Sub (Publish-Subscribe)
---------------------------

**When to use:** Broadcasting messages from one publisher to many subscribers,
with optional topic-based filtering.

:class:`~pynng.Pub0` sends messages, and :class:`~pynng.Sub0` receives them.
A subscriber must call :meth:`~pynng.Sub0.subscribe` to set which message
prefixes it wants to receive.

.. literalinclude:: /snippets/pubsub_sync.py
   :language: python

**Key options and methods:**

- :meth:`Sub0.subscribe(topic) <pynng.Sub0.subscribe>`: Subscribe to messages
  starting with ``topic`` (str or bytes). Pass ``b""`` to receive all messages.
- :meth:`Sub0.unsubscribe(topic) <pynng.Sub0.unsubscribe>`: Remove a
  subscription.
- :meth:`Sub0.subscribe_all(topics) <pynng.Sub0.subscribe_all>`: Subscribe to
  an iterable of topics in a single call.
- :meth:`Sub0.unsubscribe_all() <pynng.Sub0.unsubscribe_all>`: Unsubscribe
  from all current subscriptions atomically.
- :attr:`Sub0.subscriptions <pynng.Sub0.subscriptions>`: Return a ``frozenset``
  of current active subscriptions (as bytes).
- The ``topics`` keyword argument in the Sub0 constructor accepts a string,
  bytes, or iterable to subscribe to at creation time::

      sub = Sub0(dial=address, topics=[b"weather:", b"sports:"])

**Gotchas:**

- A subscriber with no subscriptions receives nothing at all.
- Pub/sub is "best effort." Under high load or burst traffic, messages may be
  silently dropped. Increase ``recv_buffer_size`` on the subscriber and
  ``send_buffer_size`` on the publisher if you are losing messages.
- Pub0 can only send; calling ``recv()`` raises :class:`~pynng.NotSupported`.
- Sub0 can only receive; calling ``send()`` raises :class:`~pynng.NotSupported`.
- Topic matching is a byte prefix match, not a pattern or regex.

Buffer Sizing and Best-Effort Delivery
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Pub/Sub is fundamentally a **lossy, best-effort** protocol. This is an intentional
design choice in nng: if a subscriber cannot keep up with the publisher's transmission
rate, nng drops messages rather than stalling the publisher or exhausting host memory.

- **Publisher side (``send_buffer_size``):** Determines how many outgoing messages
  can be queued in memory before nng begins discarding messages destined for slower
  pipes or congested networks. The default is 128 messages.
- **Subscriber side (``recv_buffer_size``):** Determines how many incoming messages
  can be buffered in memory waiting for application consumption (via :meth:`~pynng.Socket.recv`
  or :meth:`~pynng.Socket.arecv`). The default is 128 messages.

If your application experiences dropped messages during traffic bursts:

1. **Increase buffer depths:** Set ``send_buffer_size`` on the publisher and
   ``recv_buffer_size`` on subscribers (e.g. 512, 1024, or 4096)::

       pub = pynng.Pub0(listen=addr, send_buffer_size=1024)
       sub = pynng.Sub0(dial=addr, topics=[b""], recv_buffer_size=1024)

2. **Drain promptly in async loops:** Ensure your subscriber's receive loop is not
   blocked by slow CPU work. Offload long-running processing to worker tasks or
   threads so the receive loop can drain the socket buffer without falling behind.

Req/Rep (Request-Reply)
-----------------------

**When to use:** Client-server request/response, RPC-style communication.

:class:`~pynng.Req0` sends a request and waits for a reply.
:class:`~pynng.Rep0` receives a request and sends a reply. The protocol
enforces strict send/receive alternation.

.. literalinclude:: /snippets/reqrep_sync.py
   :language: python

**Key options:**

- :attr:`Req0.resend_time <pynng.Req0.resend_time>` (int, ms): If a reply is
  not received within this time, the request is automatically resent. The
  default is 60000 ms (1 minute). Set to ``-1`` to disable automatic resend.

**Concurrent requests with Context:**

A bare Req0/Rep0 socket can only handle one outstanding request at a time.
For concurrent requests, use :class:`~pynng.Context`:

.. code-block:: python

    import pynng

    address = "tcp://127.0.0.1:54325"

    with pynng.Rep0(listen=address) as rep, \
         pynng.Req0(dial=address) as req:

        # Create contexts for concurrent operations
        ctx1 = req.new_context()
        ctx2 = req.new_context()

        ctx1.send(b"request 1")
        ctx2.send(b"request 2")

        # Server side: use contexts to handle each independently
        rep_ctx1 = rep.new_context()
        rep_ctx2 = rep.new_context()

        msg1 = rep_ctx1.recv()
        msg2 = rep_ctx2.recv()

        rep_ctx1.send(b"reply 1")
        rep_ctx2.send(b"reply 2")

        print(ctx1.recv())  # b'reply 1'
        print(ctx2.recv())  # b'reply 2'

        # Clean up contexts
        ctx1.close()
        ctx2.close()
        rep_ctx1.close()
        rep_ctx2.close()

**Gotchas:**

- Calling ``recv()`` on a Req0 before ``send()`` raises
  :class:`~pynng.BadState`.
- Calling ``send()`` on a Rep0 before ``recv()`` raises
  :class:`~pynng.BadState`.
- :class:`~pynng.Context` is supported on :class:`~pynng.Req0`,
  :class:`~pynng.Rep0`, :class:`~pynng.Surveyor0`, and
  :class:`~pynng.Respondent0`. Other protocols raise
  :class:`~pynng.NotSupported`.
- For an asynchronous Rep0 server, consider :class:`~pynng.Rep0Service`
  (see :doc:`api/service`), which handles context pooling automatically.

Push/Pull (Pipeline)
--------------------

**When to use:** Fan-out work distribution (one producer, many workers) or
fan-in result collection (many producers, one collector).

:class:`~pynng.Push0` sends messages that are distributed round-robin among
connected :class:`~pynng.Pull0` sockets. Each message goes to exactly one
puller.

.. literalinclude:: /snippets/pushpull_sync.py
   :language: python

**Gotchas:**

- Push0 can only send; calling ``recv()`` raises :class:`~pynng.NotSupported`.
- Pull0 can only receive; calling ``send()`` raises :class:`~pynng.NotSupported`.
- Messages are load-balanced across connected pullers. There is no way to
  direct a message to a specific puller.
- Unlike pub/sub, every message is delivered to exactly one consumer, not
  broadcast to all.

Surveyor/Respondent (Survey)
----------------------------

**When to use:** Collecting responses from a group of peers within a time
window. Think "asking a question to a room" rather than a single peer.

:class:`~pynng.Surveyor0` sends a survey message to all connected
:class:`~pynng.Respondent0` sockets and collects responses until the survey
expires.

.. literalinclude:: /snippets/surveyor_sync.py
   :language: python

**Key options:**

- :attr:`Surveyor0.survey_time <pynng.Surveyor0.survey_time>` (int, ms): How
  long the survey window stays open for responses. After this time,
  ``recv()`` raises :class:`~pynng.Timeout`. The default is 1000 ms.

**Gotchas:**

- Once ``survey_time`` expires, the surveyor cannot receive any more
  responses from that survey (they are silently discarded).
- A surveyor must send a survey before it can receive responses.
- The survey pattern is inherently lossy: if a respondent is slow or
  disconnected, its response may never arrive.

Bus (Many-to-Many)
-------------------

**When to use:** Mesh-style communication where every node needs to talk to
every other node.

:class:`~pynng.Bus0` sends a message to all *directly connected* peers. To
build a full mesh, every node must connect to every other node.

.. literalinclude:: /snippets/bus0_sync.py
   :language: python

**Gotchas:**

- Messages are only delivered to directly connected peers. If node A is
  connected to node B, and node B is connected to node C, a message sent by
  A will reach B but *not* C (unless A is also directly connected to C).
- A Bus0 socket does not receive its own messages.
- For large meshes, the number of connections grows quadratically (N*(N-1)/2).

Protocol Comparison
-------------------

.. list-table::
   :header-rows: 1
   :widths: 20 15 15 50

   * - Pattern
     - Sender
     - Receiver
     - Use Case
   * - Pair0/Pair1
     - Both
     - Both
     - Simple bidirectional link between two (or a few) peers
   * - Pub0/Sub0
     - Pub0
     - Sub0
     - One-to-many broadcast with topic filtering
   * - Req0/Rep0
     - Req0 (request)
     - Rep0 (reply)
     - Client-server request/response, RPC
   * - Push0/Pull0
     - Push0
     - Pull0
     - Work distribution, pipeline processing
   * - Surveyor0/Respondent0
     - Surveyor0 (query)
     - Respondent0 (reply)
     - Group query with time-bounded response collection
   * - Bus0
     - Both
     - Both
     - Mesh network, peer-to-peer broadcast


Socket Buffer Sizing and Flow Control
-------------------------------------

Every nng socket maintains internal in-memory queues for pending send and receive
operations. Understanding how these queues behave under load is critical for building
robust systems.

Queue Capacity: Message Counts, Not Bytes
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Both :attr:`~pynng.Socket.send_buffer_size` and :attr:`~pynng.Socket.recv_buffer_size`
are configured in **number of messages**, not byte sizes:

- The default buffer size on all sockets is **128 messages**.
- To limit message sizes by bytes, use :attr:`~pynng.Socket.recv_max_size` (default 1 MB).

Delivery Semantics Under Saturation: Loss vs. Backpressure
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

The behavior when a queue reaches its capacity depends entirely on the protocol:

.. list-table::
   :header-rows: 1
   :widths: 25 15 60

   * - Protocol Family
     - Queue Full Behavior
     - Description
   * - **Pub0 / Sub0**
     - **Drops** (Lossy)
     - Messages that exceed buffer limits are silently discarded. This guarantees
       that one slow or unresponsive subscriber never stalls the publisher or blocks
       other subscribers.
   * - **Pair0 / Pair1**
     - **Backpressures** (Lossless)
     - Senders block (in sync mode) or yield (in async mode via :meth:`~pynng.Socket.asend`)
       until buffer space becomes available. If ``block=False`` is passed to :meth:`~pynng.Socket.send`,
       raises :class:`~pynng.TryAgain`.
   * - **Push0 / Pull0**
     - **Backpressures** (Lossless)
     - Senders pause when pipeline queues are full, applying backpressure upstream
       to match worker processing rates.
   * - **Req0 / Rep0**
     - **Backpressures** (Lossless)
     - Requests and replies are queued up to buffer limits before applying backpressure.
   * - **Surveyor0 / Respondent0**
     - **Backpressures** (Lossless)
     - Queries and responses pause senders when internal pipe queues are saturated.

Tuning Guidelines
^^^^^^^^^^^^^^^^^

- **For Burst Absorption:** If your application produces or receives short, intense
  bursts of data that briefly exceed steady-state throughput, increase buffer sizes
  (e.g., ``send_buffer_size=1024``, ``recv_buffer_size=1024``). This prevents packet
  loss in pub/sub and prevents transient producer pauses in pipeline protocols.
- **For Low Latency / Real-Time Data:** If you are streaming real-time sensor data,
  telemetry, or market ticks where stale messages are useless, keep buffer sizes
  small (e.g. 16 or 32). A small buffer ensures that received messages reflect the
  freshest state and minimizes queue dwell time.
- **Memory Footprint:** Each buffered message holds its payload in memory. If your
  messages are large (e.g. megabytes each), large buffer sizes (e.g. 10,000) can
  consume significant RAM. Size your buffers as a product of ``buffer_size * average_message_size``.
