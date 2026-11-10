# provide the API
from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version
import sys as _sys
import types as _types

__version__: str
try:
    __version__ = version("pynng")
except PackageNotFoundError:
    try:
        from ._version import __version__ as _scm_version

        __version__ = str(_scm_version)
    except ImportError:
        __version__ = "0.0.0"

from ._nng import ffi, lib
from . import nng as _nng_module
from .exceptions import (
    AddressInUse,
    AddressInvalid,
    AlreadyExists,
    Ambiguous,
    AuthenticationError,
    BadState,
    BadType,
    Busy,
    Canceled,
    Closed,
    ConnectionAborted,
    ConnectionRefused,
    ConnectionReset,
    CryptoError,
    DestinationUnreachable,
    Internal,
    Interrupted,
    InvalidOperation,
    MessageStateError,
    MessageTooLarge,
    NNGException,
    NoArgument,
    NoEntry,
    NoMemory,
    NotSupported,
    OutOfFiles,
    OutOfSpace,
    PermissionDenied,
    ProtocolError,
    ReadOnly,
    Stopped,
    Timeout,
    TryAgain,
    WriteOnly,
    check_err,
)
from .nng import (
    Bus0,
    Context,
    Dialer,
    Listener,
    Message,
    Pair0,
    Pair1,
    Pipe,
    PipeEvent,
    PipeEventStream,
    Pub0,
    Pull0,
    Push0,
    RawBus0,
    RawPair0,
    RawPair1,
    RawPub0,
    RawPull0,
    RawPush0,
    RawRep0,
    RawReq0,
    RawRespondent0,
    RawSub0,
    RawSurveyor0,
    Rep0,
    Req0,
    Respondent0,
    Socket,
    Sub0,
    Surveyor0,
    adevice,
    device,
    nng_fini,
    nng_fini_at_exit,
)
from .service import Rep0Service, Request
from .stats import Stat, socket_stats, stats
from .tls import TLSConfig

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
    def nng_fini_at_exit(self) -> bool:
        return _nng_module.nng_fini_at_exit

    @nng_fini_at_exit.setter
    def nng_fini_at_exit(self, value: bool) -> None:
        _nng_module.nng_fini_at_exit = value


_sys.modules[__name__].__class__ = _PynngModule
