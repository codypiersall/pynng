.. pynng documentation master file, created by
   sphinx-quickstart on Mon Aug 20 21:41:14 2018.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

This is Pynng's Documentation.
==============================

pynng is Python bindings to `Nanomsg Next Generation`_ (nng).  It provides a
nice Pythonic interface to the nng library. The goal is that pynng's interface
feels natural enough to use that you don't think of it as a wrapper, while
still exposing the power of the underlying library.  It is installable with
pip on all major platforms (Linux, Windows, macOS).  It has first class support
for `Trio`_ and :mod:`asyncio`, in addition to being able to be used
synchronously.

nng is an
implementation of the `Scalability Protocols`_; it is the spiritual successor
to `ZeroMQ`_.  There are a couple of distributed systems problems that the
scalability protocols aim to solve:

1. There are a few communication patterns that are implemented over and over
   and over and over and over again.  The wheel is continuously reinvented, but
   no implementations are compatible with each other.
2. Not only is the wheel continuosly reinvented, it is reinvented for every
   combination of *transport* and *protocol*.  A *transport* is how data gets
   from one place to another; things like TCP/IP, HTTP, Unix sockets, carrier
   pigeons.  A *protocol* is the way that both sides have agreed to communicate
   with each other (some protocols are ad-hoc, and some are more formal).

The scalability protocols are the basic tools you need to build a distributed
system.  The following **protocols** are available:

* **pair** - simple one-to-one communication. (:class:`~pynng.Pair0`,
  :class:`~pynng.Pair1`.)
* **request/response** - I ask, you answer. (:class:`~pynng.Req0`,
  :class:`~pynng.Rep0`)
* **pub/sub** - subscribers are notified of topics they are interested in.
  (:class:`~pynng.Pub0`, :class:`~pynng.Sub0`)
* **pipeline**, aka **push/pull** - load balancing.
  (:class:`~pynng.Push0`, :class:`~pynng.Pull0`)
* **survey** - query the state of multiple applications.
  (:class:`~pynng.Surveyor0`, :class:`~pynng.Respondent0`)
* **bus** - messages are sent to all connected sockets (:class:`~pynng.Bus0`)

The following **transports** are available:

* **inproc**: communication within a single process.
* **ipc**: communication across processes on a single machine.
* **tcp**: communication over networks via tcp.
* **ws**: communication over networks with websockets.  (Probably only useful if
  one end is on a browser.)
* **tls+tcp**: Encrypted `TLS`_ communication over networks.
* **carrier pigeons**: communication via World War 1-style `carrier pigeons`_.
  The latency is pretty high on this one.

These protocols are language-agnostic, and `implementations exist for many
languages <https://nanomsg.org/documentation.html#_language_bindings>`_.

This library is available under the `MIT License`_ and the source is available
on `GitHub`_.

If you need two processes to talk to each other—either locally or remotely—you
should be using the scalability protocols. You never need to open another plain
`socket`_ again.

Okay, that was a little hyperbolic.  But give pynng a chance; you might like
it.

Installing pynng
----------------

On Linux, Windows, and macOS, a quick

.. code-block:: python

   pip3 install pynng

should do the trick.  pynng works on Python 3.5+.


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
.. _TLS: https://en.wikipedia.org/wiki/Transport_Layer_Security
.. _MIT License: https://github.com/codypiersall/pynng/blob/master/LICENSE.txt
.. _GitHub: https://github.com/codypiersall/pynng
.. _Trio: https://trio.readthedocs.io
