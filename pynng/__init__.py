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

from .stats import stats, Stat
from .service import Rep0Service, Request  # noqa: F401
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
