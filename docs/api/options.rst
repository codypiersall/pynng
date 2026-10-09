Options
=======

pynng uses Python descriptors to expose NNG socket options as properties on
socket, dialer, listener, pipe, and context objects. You typically interact
with options as regular Python attributes rather than calling getter/setter
functions directly.

For example::

   with pynng.Pair0(listen='tcp://127.0.0.1:5555') as sock:
       # Get the receive timeout (milliseconds)
       timeout = sock.recv_timeout

       # Set the receive timeout
       sock.recv_timeout = 1000

Option Descriptor
-----------------

.. autoclass:: pynng.nng._NNGOption
   :members:

Internal Option Functions
-------------------------

These functions are used internally by the option descriptors. They are
documented here for completeness but are not part of the public API.

.. autofunction:: pynng.options._getopt_int
.. autofunction:: pynng.options._setopt_int
.. autofunction:: pynng.options._getopt_string
.. autofunction:: pynng.options._getopt_bool
.. autofunction:: pynng.options._getopt_ms
.. autofunction:: pynng.options._setopt_ms
.. autofunction:: pynng.options._getopt_size
.. autofunction:: pynng.options._setopt_size
.. autofunction:: pynng.options._getopt_sockaddr
