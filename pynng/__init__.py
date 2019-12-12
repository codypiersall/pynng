# provide the API
from ._version import __version__
from ._nng import lib, ffi
from .nng import (
    Bus0,
    Pair0,
    Pair1,
    Pull0, Push0,
    Pub0, Sub0,
    Req0, Rep0,
    Surveyor0, Respondent0,

    Context,
    Socket,
    Listener,
    Dialer,
    Pipe,
    Message,
)

from .tls import TLSConfig

from .exceptions import (
    NNGException,
    Interrupted,
    NoMemory,
    InvalidOperation,
    Busy,
    Timeout,
    ConnectionRefused,
    Closed,
    TryAgain,
    NotSupported,
    AddressInUse,
    BadState,
    NoEntry,
    ProtocolError,
    DestinationUnreachable,
    AddressInvalid,
    PermissionDenied,
    MessageTooLarge,
    ConnectionReset,
    ConnectionAborted,
    Canceled,
    OutOfFiles,
    OutOfSpace,
    AlreadyExists,
    ReadOnly,
    WriteOnly,
    CryptoError,
    AuthenticationError,
    NoArgument,
    Ambiguous,
    BadType,
    Internal,
    check_err,
    MessageStateError
)
