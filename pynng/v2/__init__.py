"""
pynng.v2 -- nng v2 protocol bindings for Python.

.. warning::

    nng v2 is experimental/alpha. The API may change between releases.
    This module requires the ``_nng_v2`` CFFI extension to be built.

This module provides the same protocol classes as ``pynng`` (v1), but backed
by nng v2 (pinned to ``v2.1.0`` by default; ``pynng`` 1.x defaults to nng v1
at ``import pynng``, while ``pynng`` 2.0 will make nng v2 the top-level default).
Both v1 and v2 can coexist in the same process.

Usage::

    import pynng.v2 as v2

    with v2.Req0(dial="tcp://localhost:5555") as req:
        req.send(b"hello")
        reply = req.recv()

Key differences from v1:

- No ``name`` property on sockets (``NNG_OPT_SOCKNAME`` removed)
- No ``NNG_FLAG_ALLOC``; recv uses ``nng_recvmsg()`` internally
- ``Sub0.subscribe()``/``unsubscribe()`` use dedicated v2 functions
- TLS is configured per endpoint (dialer/listener); a socket's ``tls_config``
  is only the default for its endpoints whose transport has TLS
- Socket properties (``protocol``, ``peer``, ``raw``, etc.) use dedicated
  v2 getter functions instead of generic option accessors
"""

from __future__ import annotations

import sys as _sys
import types as _types

try:
    from pynng._nng_v2 import ffi as _ffi, lib as _lib
except ImportError as exc:
    raise ImportError(
        "pynng.v2 requires the _nng_v2 CFFI extension module, which was not "
        "found. This extension is built when BUILD_NNG_V2=ON (the default) "
        "is set during the pynng build. Rebuild pynng with v2 support enabled: "
        "pip install -e . (or pip install pynng with a v2-capable build)."
    ) from exc

from .. import __version__
from .._base import _mark_nng_initialized

lib = _lib
ffi = _ffi

# Initialize nng v2 runtime. Must be called before any v2 operations.
_lib.nng_init(_ffi.NULL)
_mark_nng_initialized()

from pynng.tls import _register_lib  # noqa: E402

_register_lib(_lib, _ffi)

# Import v2 callbacks module to register the ffi.def_extern callbacks.
# This must happen before any v2 socket is created.
from . import _callbacks, nng as _nng_v2_module  # noqa: F401, E402

# Import v2 protocol classes
from .nng import (  # noqa: E402
    Socket,
    Bus0,
    Pair0,
    Pair1,
    Push0,
    Pull0,
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
    Dialer,
    Listener,
    Pipe,
    PipeEvent,
    PipeEventStream,
    Message,
    TLSConfig,
    Rep0Service,
    device,
    adevice,
    nng_fini,
    nng_fini_at_exit,
    stats,
    socket_stats,
    Stat,
)

# Import shared exceptions (same for v1 and v2)
from pynng.exceptions import (  # noqa: E402
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

# Import service classes (optional / decoupled)
try:
    from pynng.service import Request
except ImportError:
    pass

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


class _PynngV2Module(_types.ModuleType):
    # The atexit handler reads pynng.v2.nng.nng_fini_at_exit. A plain copy here
    # would make "pynng.v2.nng_fini_at_exit = True" have no effect.
    @property
    def nng_fini_at_exit(self) -> bool:
        return _nng_v2_module.nng_fini_at_exit

    @nng_fini_at_exit.setter
    def nng_fini_at_exit(self, value: bool) -> None:
        _nng_v2_module.nng_fini_at_exit = value

    @property
    def _finalized(self) -> bool:
        return _nng_v2_module._finalized

    @_finalized.setter
    def _finalized(self, value: bool) -> None:
        _nng_v2_module._finalized = value


_sys.modules[__name__].__class__ = _PynngV2Module
