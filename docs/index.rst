pynng -- Python bindings for NNG
================================

pynng provides Python bindings for `NNG <https://nng.nanomsg.org>`_
(nanomsg next generation), a lightweight messaging library that supports
common communication patterns (pub/sub, req/rep, push/pull, pair, bus, survey).

pynng supports both synchronous and asynchronous usage with ``asyncio`` and
``trio``.

.. toctree::
   :maxdepth: 2
   :caption: Getting Started

   installation
   getting-started

.. toctree::
   :maxdepth: 2
   :caption: User Guide

   protocols
   async
   transports
   tls

.. toctree::
   :maxdepth: 2
   :caption: API Reference

   api/sockets
   api/messaging
   api/networking
   api/tls
   api/sockaddr
   api/exceptions
   api/options

.. toctree::
   :maxdepth: 1
   :caption: Project

   contributing
   architecture
   migration
   changelog
   developing
