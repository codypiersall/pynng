Exceptions
==========

pynng translates all NNG error codes into Python exceptions. The root
exception of the hierarchy is :class:`~pynng.NNGException`, which inherits
from :class:`Exception`. All other exceptions defined in pynng inherit from
``NNGException``.

.. automodule:: pynng.exceptions
   :members:
   :undoc-members:
   :show-inheritance:

Exception Reference Table
-------------------------

The following table maps pynng exceptions to their NNG error codes:

+----------------------------+----------------------+--------------------------------------------------+
| pynng Exception            | nng error code       | Description                                      |
+============================+======================+==================================================+
| ``Interrupted``            | ``NNG_EINTR``        | The call was interrupted.                        |
+----------------------------+----------------------+--------------------------------------------------+
| ``NoMemory``               | ``NNG_ENOMEM``       | Not enough memory to complete the operation.     |
+----------------------------+----------------------+--------------------------------------------------+
| ``InvalidOperation``       | ``NNG_EINVAL``       | An invalid operation was requested.              |
+----------------------------+----------------------+--------------------------------------------------+
| ``Busy``                   | ``NNG_EBUSY``        | The resource is busy.                            |
+----------------------------+----------------------+--------------------------------------------------+
| ``Timeout``                | ``NNG_ETIMEDOUT``    | The operation timed out.                         |
+----------------------------+----------------------+--------------------------------------------------+
| ``ConnectionRefused``      | ``NNG_ECONNREFUSED`` | The remote socket refused a connection.          |
+----------------------------+----------------------+--------------------------------------------------+
| ``Closed``                 | ``NNG_ECLOSED``      | The resource was already closed.                 |
+----------------------------+----------------------+--------------------------------------------------+
| ``TryAgain``               | ``NNG_EAGAIN``       | Non-blocking mode was requested but would block. |
+----------------------------+----------------------+--------------------------------------------------+
| ``NotSupported``           | ``NNG_ENOTSUP``      | The operation is not supported on the socket.    |
+----------------------------+----------------------+--------------------------------------------------+
| ``AddressInUse``           | ``NNG_EADDRINUSE``   | The requested address is already in use.         |
+----------------------------+----------------------+--------------------------------------------------+
| ``BadState``               | ``NNG_ESTATE``       | Operation attempted in a bad state.              |
+----------------------------+----------------------+--------------------------------------------------+
| ``NoEntry``                | ``NNG_ENOENT``       | The requested resource does not exist.           |
+----------------------------+----------------------+--------------------------------------------------+
| ``ProtocolError``          | ``NNG_EPROTO``       | A protocol error occurred.                       |
+----------------------------+----------------------+--------------------------------------------------+
| ``DestinationUnreachable`` | ``NNG_EUNREACHABLE`` | Could not reach the destination.                 |
+----------------------------+----------------------+--------------------------------------------------+
| ``AddressInvalid``         | ``NNG_EADDRINVAL``   | An invalid address was specified.                |
+----------------------------+----------------------+--------------------------------------------------+
| ``PermissionDenied``       | ``NNG_EPERM``        | Permission denied.                               |
+----------------------------+----------------------+--------------------------------------------------+
| ``MessageTooLarge``        | ``NNG_EMSGSIZE``     | The message is too large.                        |
+----------------------------+----------------------+--------------------------------------------------+
| ``ConnectionReset``        | ``NNG_ECONNRESET``   | The connection was reset by the peer.            |
+----------------------------+----------------------+--------------------------------------------------+
| ``ConnectionAborted``      | ``NNG_ECONNABORTED`` | The connection was aborted.                      |
+----------------------------+----------------------+--------------------------------------------------+
| ``Canceled``               | ``NNG_ECANCELED``    | The operation was canceled.                      |
+----------------------------+----------------------+--------------------------------------------------+
| ``OutOfFiles``             | ``NNG_ENOFILES``     | Out of file descriptors.                         |
+----------------------------+----------------------+--------------------------------------------------+
| ``OutOfSpace``             | ``NNG_ENOSPC``       | Out of storage space.                            |
+----------------------------+----------------------+--------------------------------------------------+
| ``AlreadyExists``          | ``NNG_EEXIST``       | The resource already exists.                     |
+----------------------------+----------------------+--------------------------------------------------+
| ``ReadOnly``               | ``NNG_EREADONLY``    | The option is read-only.                         |
+----------------------------+----------------------+--------------------------------------------------+
| ``WriteOnly``              | ``NNG_EWRITEONLY``   | The option is write-only.                        |
+----------------------------+----------------------+--------------------------------------------------+
| ``CryptoError``            | ``NNG_ECRYPTO``      | A cryptographic error occurred.                  |
+----------------------------+----------------------+--------------------------------------------------+
| ``AuthenticationError``    | ``NNG_EPEERAUTH``    | Peer authentication failed.                      |
+----------------------------+----------------------+--------------------------------------------------+
| ``NoArgument``             | ``NNG_ENOARG``       | A required argument is missing.                  |
+----------------------------+----------------------+--------------------------------------------------+
| ``Ambiguous``              | ``NNG_EAMBIGUOUS``   | The operation is ambiguous.                      |
+----------------------------+----------------------+--------------------------------------------------+
| ``BadType``                | ``NNG_EBADTYPE``     | An incorrect type was provided.                  |
+----------------------------+----------------------+--------------------------------------------------+
| ``Internal``               | ``NNG_EINTERNAL``    | An internal error occurred.                      |
+----------------------------+----------------------+--------------------------------------------------+
