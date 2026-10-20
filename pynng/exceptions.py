"""
Exception hierarchy for pynng.  The base of the hierarchy is NNGException.
Every exception has a corresponding errno attribute which can be checked.

Generally, each number in nng_errno_enum corresponds with an Exception type.


"""

from ._nng import ffi as _default_ffi, lib as _default_lib


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


class Stopped(NNGException):  # NNG_ESTOPPED (v2 only, value 999)
    pass


# Build the exception map using numeric constants extracted from v1 lib.
# These integer values are stable across v1 and v2.
EXCEPTION_MAP = {
    int(_default_lib.NNG_EINTR): Interrupted,
    int(_default_lib.NNG_ENOMEM): NoMemory,
    int(_default_lib.NNG_EINVAL): InvalidOperation,
    int(_default_lib.NNG_EBUSY): Busy,
    int(_default_lib.NNG_ETIMEDOUT): Timeout,
    int(_default_lib.NNG_ECONNREFUSED): ConnectionRefused,
    int(_default_lib.NNG_ECLOSED): Closed,
    int(_default_lib.NNG_EAGAIN): TryAgain,
    int(_default_lib.NNG_ENOTSUP): NotSupported,
    int(_default_lib.NNG_EADDRINUSE): AddressInUse,
    int(_default_lib.NNG_ESTATE): BadState,
    int(_default_lib.NNG_ENOENT): NoEntry,
    int(_default_lib.NNG_EPROTO): ProtocolError,
    int(_default_lib.NNG_EUNREACHABLE): DestinationUnreachable,
    int(_default_lib.NNG_EADDRINVAL): AddressInvalid,
    int(_default_lib.NNG_EPERM): PermissionDenied,
    int(_default_lib.NNG_EMSGSIZE): MessageTooLarge,
    int(_default_lib.NNG_ECONNRESET): ConnectionReset,
    int(_default_lib.NNG_ECONNABORTED): ConnectionAborted,
    int(_default_lib.NNG_ECANCELED): Canceled,
    int(_default_lib.NNG_ENOFILES): OutOfFiles,
    int(_default_lib.NNG_ENOSPC): OutOfSpace,
    int(_default_lib.NNG_EEXIST): AlreadyExists,
    int(_default_lib.NNG_EREADONLY): ReadOnly,
    int(_default_lib.NNG_EWRITEONLY): WriteOnly,
    int(_default_lib.NNG_ECRYPTO): CryptoError,
    int(_default_lib.NNG_EPEERAUTH): AuthenticationError,
    int(_default_lib.NNG_ENOARG): NoArgument,
    int(_default_lib.NNG_EAMBIGUOUS): Ambiguous,
    int(_default_lib.NNG_EBADTYPE): BadType,
    int(_default_lib.NNG_EINTERNAL): Internal,
}

# Add NNG_ESTOPPED (999) for v2 support. This code only exists in v2,
# but we add it to the map unconditionally with its known numeric value.
EXCEPTION_MAP[999] = Stopped


class MessageStateError(Exception):
    """
    Indicates that a Message was trying to be used in an invalid way.
    """


def check_err(err, lib=None, ffi=None):
    """
    Raises an exception if the return value of an nng_function is nonzero.

    The enum nng_errno_enum is defined in nng.h

    Args:
        err: The error code returned by an NNG function.
        lib: The CFFI lib to use for nng_strerror. Defaults to v1 lib.
        ffi: The CFFI ffi to use for string conversion. Defaults to v1 ffi.
    """
    # fast path for success
    if not err:
        return

    if lib is None:
        lib = _default_lib
    if ffi is None:
        ffi = _default_ffi

    msg = lib.nng_strerror(err)
    string = ffi.string(msg)
    string = string.decode()
    exc = EXCEPTION_MAP.get(err, NNGException)
    raise exc(string, err)
