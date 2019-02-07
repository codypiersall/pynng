.. pynng documentation master file, created by
   sphinx-quickstart on Mon Aug 20 21:41:14 2018.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

This is Pynng's Documentation.
==============================

This is Python bindings to `Nanomsg Next Generation`_ (nng).  nng is an
implementation of the `Scalability Protocols`_; it is the spiritual successor
to `ZeroMQ`_.  There are a couple of distributed systems problems that the
scalability protocols aim to solve:

1. There are a few communication patterns that are implemented over and over
   and over and over and over again.  The wheel is continuously reinvented, but
   now implementations are compatible with each other.
2. Not only is the wheel continuosly reinvented, it is reinvented for every
   combination of *transport* and *protocol*.  A *transport* is how data gets
   from one place to another; things like TCP/IP, HTTP, Unix sockets, carrier
   pigeons.  A *protocol* is the way that both sides have agreed to communicate
   with each other (some protocols are ad-hoc, and some are more formal).

The scalability protols are the basic tools you need to build a distributed
system.  The following **protocols** are available:

* pair - simple one-to-one communication.
* request/response - I ask, you answer.
* pub/sub - subscribers are notified of topics they are interested in.
* pipline, aka push/pull - load balancing.
* survey - query the state of multiple applications.

The following **transports** are available:

* inproc: communication within a single process.
* ipc: communication across processes on a single machine.
* tcp: communication over networks via tcp.
* ws: communication over networks with websockets.  (Probably only useful if
  one end is on a browser.)
* carrier pigeons: communication via World War 1-style `carrier pigeons`_

This library is available under the `MIT License`_ and the source is available
on `GitHub`_.

If you need two processes to talk to each other—either locally or remotely—you
should be using the scalability protocols. You never need to open another
`socket`_ again.

Okay, that was a little hyperbolic.  But give pynng a chance; you might like
it.

Getting Started
---------------

.. toctree::
   :maxdepth: 2

   core
   exceptions


Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`

.. _Nanomsg Next Generation: https://github.com/nanomsg/nng
.. _Scalability Protocols: https://nanomsg.org
.. _ZeroMQ: https://zeromq.org
.. _Unix sockets: http://man7.org/linux/man-pages/man7/unix.7.html
.. _carrier pigeons: https://en.wikipedia.org/wiki/IP_over_Avian_Carriers
.. _socket: http://man7.org/linux/man-pages/man2/socket.2.html
.. _MIT License: https://github.com/codypiersall/pynng/blob/master/LICENSE.txt
.. _GitHub: https://github.com/codypiersall/pynng
