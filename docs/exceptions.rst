Exceptions in pynng
===================

pynng translates all of NNG error codes into Python Exceptions.  The root
exception of the hierarchy is the ``NNGException``; ``NNGException`` inherits
from Exception, and all other exceptions defined in this library inherit from
``NNGException``.

The following table describes all the exceptions defined by pynng.  The first
column is the name of the exception in pynng (defined in ``pynng.exceptions``),
the second is the nng error code (defined in ``nng.h``), and the third is a
description of the exception.

+----------------------------+----------------------+--------------------------------------------------+
| pynng Exception            | nng error code       | Description                                      |
+============================+======================+==================================================+
| ``Interrupted``            | ``NNG_EINTR``        | The call was interrupted; if this happens,       |
|                            |                      | Python may throw a KeyboardInterrupt.  (I'm not  |
|                            |                      | sure if this is an exception you can even get    |
|                            |                      | with these bindings)                             |
+----------------------------+----------------------+--------------------------------------------------+
| ``NoMemory``               | ``NNG_ENOMEM``       | Not enough memory to complete the operation.     |
+----------------------------+----------------------+--------------------------------------------------+
| ``InvalidOperation``       | ``NNG_EINVAL``       | An invalid operation was requested on the        |
|                            |                      | resource.                                        |
+----------------------------+----------------------+--------------------------------------------------+
| ``Busy``                   | ``NNG_EBUSY``        |                                                  |
+----------------------------+----------------------+--------------------------------------------------+
| ``Timeout``                | ``NNG_ETIMEDOUT``    | The operation timed out.  Some operations        |
|                            |                      | cannot time out; an example that cannot time     |
|                            |                      | out is a ``send()`` on a ``Pub0`` socket         |
+----------------------------+----------------------+--------------------------------------------------+
| ``ConnectionRefused``      | ``NNG_ECONNREFUSED`` | The remote socket refused a connection.          |
+----------------------------+----------------------+--------------------------------------------------+
| ``Closed``                 | ``NNG_ECLOSED``      | The resource was already closed and cannot       |
|                            |                      | complete the requested operation.                |
+----------------------------+----------------------+--------------------------------------------------+
| ``TryAgain``               | ``NNG_EAGAIN``       | The requested operation would block, but         |
|                            |                      | non-blocking mode was requested.                 |
+----------------------------+----------------------+--------------------------------------------------+
| ``NotSupported``           | ``NNG_ENOTSUP``      | The operation is not supported on the socket.    |
|                            |                      | For example, attempting to ``send`` on a         |
|                            |                      | ``Sub0`` socket will raise this.                 |
+----------------------------+----------------------+--------------------------------------------------+
| ``AddressInUse``           | ``NNG_EADDRINUSE``   | The requested address is already in use and      |
|                            |                      | cannot be bound to.  This happens if multiple    |
|                            |                      | sockets attempt to ``listen()`` at the same      |
|                            |                      | address.                                         |
+----------------------------+----------------------+--------------------------------------------------+
| ``BadState``               | ``NNG_ESTATE``       | An operation was attempted in a bad state; for   |
|                            |                      | example, attempting to ``recv()`` twice in a     |
|                            |                      | row of a  single ``Req0`` socket.                |
+----------------------------+----------------------+--------------------------------------------------+
| ``NoEntry``                | ``NNG_ENOENT``       | The requested resource does not exist.           |
+----------------------------+----------------------+--------------------------------------------------+
| ``ProtocolError``          | ``NNG_EPROTO``       |                                                  |
+----------------------------+----------------------+--------------------------------------------------+
| ``DestinationUnreachable`` | ``NNG_EUNREACHABLE`` | Could not reach the destination.                 |
+----------------------------+----------------------+--------------------------------------------------+
| ``AddressInvalid``         | ``NNG_EADDRINVAL``   | An invalid address was specified.  For example,  |
|                            |                      | attempting to listen on ``"tcp://127.0.0.1:-1"`` |
|                            |                      | will throw.                                      |
+----------------------------+----------------------+--------------------------------------------------+
| ``PermissionDenied``       | ``NNG_EPERM``        | You did not have permission to do the requested  |
|                            |                      | operation.                                       |
+----------------------------+----------------------+--------------------------------------------------+
| ``MessageTooLarge``        | ``NNG_EMSGSiZE``     |                                                  |
+----------------------------+----------------------+--------------------------------------------------+
| ``ConnectionReset``        | ``NNG_ECONNRESET``   |                                                  |
+----------------------------+----------------------+--------------------------------------------------+
| ``ConnectionAborted``      | ``NNG_ECONNABORTED`` |                                                  |
+----------------------------+----------------------+--------------------------------------------------+
| ``Canceled``               | ``NNG_ECANCELED``    |                                                  |
+----------------------------+----------------------+--------------------------------------------------+
| ``OutOfFiles``             | ``NNG_ENOFILES``     |                                                  |
+----------------------------+----------------------+--------------------------------------------------+
| ``OutOfSpace``             | ``NNG_ENOSPC``       |                                                  |
+----------------------------+----------------------+--------------------------------------------------+
| ``AlreadyExists``          | ``NNG_EEXIST``       |                                                  |
+----------------------------+----------------------+--------------------------------------------------+
| ``ReadOnly``               | ``NNG_EREADONLY``    |                                                  |
+----------------------------+----------------------+--------------------------------------------------+
| ``WriteOnly``              | ``NNG_EWRITEONLY``   |                                                  |
+----------------------------+----------------------+--------------------------------------------------+
| ``CryptoError``            | ``NNG_ECRYPTO``      |                                                  |
+----------------------------+----------------------+--------------------------------------------------+
| ``AuthenticationError``    | ``NNG_EPEERAUTH``    |                                                  |
+----------------------------+----------------------+--------------------------------------------------+
| ``NoArgument``             | ``NNG_ENOARG``       |                                                  |
+----------------------------+----------------------+--------------------------------------------------+
| ``Ambiguous``              | ``NNG_EAMBIGUOUS``   |                                                  |
+----------------------------+----------------------+--------------------------------------------------+
| ``BadType``                | ``NNG_EBADTYPE``     |                                                  |
+----------------------------+----------------------+--------------------------------------------------+
| ``Internal``               | ``NNG_EINTERNAL``    |                                                  |
+----------------------------+----------------------+--------------------------------------------------+
