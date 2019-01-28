"""
Exception hierarchy for pynng.  The base of the hierarchy is NNGException.
Every exception has a corresponding errno attribute which can be checked.

Generally, each number in nng_errno_enum corresponds with an Exception type.


"""

from ._nng import ffi, lib as nng


class NNGException(Exception):
    """The base exception for any exceptional condition in the nng bindings."""
    def __init__(self, msg, errno):
        super().__init__(msg)
        self.errno = errno


class Interrupted(NNGException):  # NNG_EINTR
    pass


class NoMemory(NNGException):  # NNG_ENOMEM
    pass


class InvalidOperation(NNGException):  # NNG_EINVAL
    pass


class Busy(NNGException):  # NNG_EBUSY
    pass


class Timeout(NNGException):  # NNG_ETIMEDOUT
    pass


class ConnectionRefused(NNGException):  # NNG_ECONNREFUSED
    pass


class Closed(NNGException):  # NNG_ECLOSED
    pass


class TryAgain(NNGException):  # NNG_EAGAIN
    pass


class NotSupported(NNGException):  # NNG_ENOTSUP
    pass


class AddressInUse(NNGException):  # NNG_EADDRINUSE
    pass


class BadState(NNGException):  # NNG_ESTATE
    pass


class NoEntry(NNGException):  # NNG_ENOENT
    pass


class ProtocolError(NNGException):  # NNG_EPROTO
    pass


class DestinationUnreachable(NNGException):  # NNG_EUNREACHABLE
    pass


class AddressInvalid(NNGException):  # NNG_EADDRINVAL
    pass


class PermissionDenied(NNGException):  # NNG_EPERM
    pass


class MessageTooLarge(NNGException):  # NNG_EMSGSiZE
    pass


class ConnectionReset(NNGException):  # NNG_ECONNRESET
    pass


class ConnectionAborted(NNGException):  # NNG_ECONNABORTED
    pass


class Canceled(NNGException):  # NNG_ECANCELED
    pass


class OutOfFiles(NNGException):  # NNG_ENOFILES
    pass


class OutOfSpace(NNGException):  # NNG_ENOSPC
    pass


class AlreadyExists(NNGException):  # NNG_EEXIST
    pass


class ReadOnly(NNGException):  # NNG_EREADONLY
    pass


class WriteOnly(NNGException):  # NNG_EWRITEONLY
    pass


class CryptoError(NNGException):  # NNG_ECRYPTO
    pass


class AuthenticationError(NNGException):  # NNG_EPEERAUTH
    pass


class NoArgument(NNGException):  # NNG_ENOARG
    pass


class Ambiguous(NNGException):  # NNG_EAMBIGUOUS
    pass


class BadType(NNGException):  # NNG_EBADTYPE
    pass


class Internal(NNGException):  # NNG_EINTERNAL
    pass


# maps exceptions from the enum nng_errno_enum to Exception classes
EXCEPTION_MAP = {
    nng.NNG_EINTR: Interrupted,
    nng.NNG_ENOMEM: NoMemory,
    nng.NNG_EINVAL: InvalidOperation,
    nng.NNG_EBUSY: Busy,
    nng.NNG_ETIMEDOUT: Timeout,
    nng.NNG_ECONNREFUSED: ConnectionRefused,
    nng.NNG_ECLOSED: Closed,
    nng.NNG_EAGAIN: TryAgain,
    nng.NNG_ENOTSUP: NotSupported,
    nng.NNG_EADDRINUSE: AddressInUse,
    nng.NNG_ESTATE: BadState,
    nng.NNG_ENOENT: NoEntry,
    nng.NNG_EPROTO: ProtocolError,
    nng.NNG_EUNREACHABLE: DestinationUnreachable,
    nng.NNG_EADDRINVAL: AddressInvalid,
    nng.NNG_EPERM: PermissionDenied,
    nng.NNG_EMSGSIZE: MessageTooLarge,
    nng.NNG_ECONNRESET: ConnectionReset,
    nng.NNG_ECONNABORTED: ConnectionAborted,
    nng.NNG_ECANCELED: Canceled,
    nng.NNG_ENOFILES: OutOfFiles,
    nng.NNG_ENOSPC: OutOfSpace,
    nng.NNG_EEXIST: AlreadyExists,
    nng.NNG_EREADONLY: ReadOnly,
    nng.NNG_EWRITEONLY: WriteOnly,
    nng.NNG_ECRYPTO: CryptoError,
    nng.NNG_EPEERAUTH: AuthenticationError,
    nng.NNG_ENOARG: NoArgument,
    nng.NNG_EAMBIGUOUS: Ambiguous,
    nng.NNG_EBADTYPE: BadType,
    nng.NNG_EINTERNAL: Internal,
}


class MessageStateError(Exception):
    """
    Indicates that a Message was trying to be used in an invalid way.
    """


def check_err(err):
    """
    Raises an exception if the return value of an nng_function is nonzero.

    The enum nng_errno_enum is defined in nng.h

    """
    # fast path for success
    if not err:
        return

    msg = nng.nng_strerror(err)
    string = ffi.string(msg)
    string = string.decode()
    exc = EXCEPTION_MAP.get(err, NNGException)
    raise exc(string, err)


