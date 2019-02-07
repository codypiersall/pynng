==========================
Pynng's core functionality
==========================

At the heart of pynng is the :class:`pynng.Socket`.  It takes no positional
arguments, and all keyword arguments are optional.

----------
The Socket
----------

.. Note::

    You should never instantiate a :class:`pynng.Socket` directly.  Rather, you
    should instantiate one of the `subclasses <Available Protocols>`_.

.. autoclass:: pynng.Socket(*, listen=None, dial=None, **kwargs)
   :members: listen, dial, send, recv, asend, arecv

Feel free to peruse the `examples online
<https://github.com/codypiersall/pynng/tree/master/examples>`_, or ask in the
`gitter channel <https://gitter.im/nanomsg/nanomsg>`_.

-------------------
Available Protocols
-------------------

.. autoclass:: pynng.Pair0(**kwargs)
.. autoclass:: pynng.Pair1
.. autoclass:: pynng.Req0(**kwargs)
.. autoclass:: pynng.Rep0(**kwargs)
.. autoclass:: pynng.Pub0(**kwargs)
.. autoclass:: pynng.Sub0(**kwargs)
.. autoclass:: pynng.Push0(**kwargs)
.. autoclass:: pynng.Pull0(**kwargs)
.. autoclass:: pynng.Surveyor0(**kwargs)
.. autoclass:: pynng.Respondent0(**kwargs)

