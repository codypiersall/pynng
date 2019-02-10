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
.. autoclass:: pynng.Pair1(polyamorous=False, **kwargs)
.. autoclass:: pynng.Req0(**kwargs)
.. autoclass:: pynng.Rep0(**kwargs)
.. autoclass:: pynng.Pub0(**kwargs)
.. autoclass:: pynng.Sub0(**kwargs)
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
   :members: send, asend, recv, arecv, recv_msg, arecv_msg

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
