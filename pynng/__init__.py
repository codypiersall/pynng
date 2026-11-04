# provide the API
import sys as _sys
import types as _types
from importlib.metadata import version, PackageNotFoundError

try:
    __version__ = version("pynng")
except PackageNotFoundError:
    try:
        from ._version import __version__
    except ImportError:
        __version__ = "0.0.0"

from ._nng import lib, ffi
from .nng import (
    Bus0,
    Pair0,
    Pair1,
    Pull0,
    Push0,
    Pub0,
    Sub0,
    Req0,
    Rep0,
    Surveyor0,
    Respondent0,
    RawBus0,
    RawPair0,
    RawPair1,
    RawPush0,
    RawPull0,
    RawPub0,
    RawSub0,
    RawReq0,
    RawRep0,
    RawSurveyor0,
    RawRespondent0,
    Context,
    Socket,
    Listener,
    Dialer,
    Pipe,
    PipeEvent,
    PipeEventStream,
    Message,
    device,
    adevice,
    nng_fini,
)
from . import nng as _nng_module

from .stats import stats, socket_stats, Stat
from .service import Rep0Service, Request
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
    Stopped,
    check_err,
    MessageStateError,
)

__all__ = [
    "AddressInUse",
    "AddressInvalid",
    "AlreadyExists",
    "Ambiguous",
    "AuthenticationError",
    "BadState",
    "BadType",
    "Bus0",
    "Busy",
    "Canceled",
    "Closed",
    "ConnectionAborted",
    "ConnectionRefused",
    "ConnectionReset",
    "Context",
    "CryptoError",
    "DestinationUnreachable",
    "Dialer",
    "Internal",
    "Interrupted",
    "InvalidOperation",
    "Listener",
    "Message",
    "MessageStateError",
    "MessageTooLarge",
    "NNGException",
    "NoArgument",
    "NoEntry",
    "NoMemory",
    "NotSupported",
    "OutOfFiles",
    "OutOfSpace",
    "Pair0",
    "Pair1",
    "PermissionDenied",
    "Pipe",
    "PipeEvent",
    "PipeEventStream",
    "ProtocolError",
    "Pub0",
    "Pull0",
    "Push0",
    "RawBus0",
    "RawPair0",
    "RawPair1",
    "RawPub0",
    "RawPull0",
    "RawPush0",
    "RawRep0",
    "RawReq0",
    "RawRespondent0",
    "RawSub0",
    "RawSurveyor0",
    "ReadOnly",
    "Rep0",
    "Rep0Service",
    "Req0",
    "Request",
    "Respondent0",
    "Socket",
    "Stat",
    "Stopped",
    "Sub0",
    "Surveyor0",
    "TLSConfig",
    "Timeout",
    "TryAgain",
    "WriteOnly",
    "__version__",
    "adevice",
    "check_err",
    "device",
    "ffi",
    "lib",
    "nng_fini",
    "nng_fini_at_exit",
    "socket_stats",
    "stats",
]


class _PynngModule(_types.ModuleType):
    # The atexit handler reads pynng.nng.nng_fini_at_exit. A plain copy here
    # would make "pynng.nng_fini_at_exit = True" have no effect.
    @property
    def nng_fini_at_exit(self):
        return _nng_module.nng_fini_at_exit

    @nng_fini_at_exit.setter
    def nng_fini_at_exit(self, value):
        _nng_module.nng_fini_at_exit = value


_sys.modules[__name__].__class__ = _PynngModule
