"""
pynng.v2 -- nng v2 protocol bindings for Python.

.. warning::

    nng v2 is experimental/alpha. The API may change between releases.
    This module requires the ``_nng_v2`` CFFI extension to be built.

This module provides the same protocol classes as ``pynng`` (v1), but backed
by nng v2. Both v1 and v2 can coexist in the same process.

Usage::

    import pynng.v2 as v2

    with v2.Req0(dial="tcp://localhost:5555") as req:
        req.send(b"hello")
        reply = req.recv()

Key differences from v1:

- No ``name`` property on sockets (``NNG_OPT_SOCKNAME`` removed)
- No ``NNG_FLAG_ALLOC``; recv uses ``nng_recvmsg()`` internally
- ``Sub0.subscribe()``/``unsubscribe()`` use dedicated v2 functions
- TLS is configured per-endpoint (dialer/listener), not per-socket
- Socket properties (``protocol``, ``peer``, ``raw``, etc.) use dedicated
  v2 getter functions instead of generic option accessors
"""

import atexit

try:
    from pynng._nng_v2 import lib as _lib, ffi as _ffi
except ImportError as exc:
    raise ImportError(
        "pynng.v2 requires the _nng_v2 CFFI extension module, which was not "
        "found. This extension is built when BUILD_NNG_V2=ON (the default) "
        "is set during the pynng build. Rebuild pynng with v2 support enabled: "
        "pip install -e . (or pip install pynng with a v2-capable build)."
    ) from exc

# Initialize nng v2 runtime. Must be called before any v2 operations.
_lib.nng_init(_ffi.NULL)


def _pynng_v2_atexit():
    _lib.nng_fini()


atexit.register(_pynng_v2_atexit)

# Import v2 callbacks module to register the ffi.def_extern callbacks.
# This must happen before any v2 socket is created.
from . import _callbacks  # noqa: F401, E402

# Import v2 protocol classes
from .nng import (  # noqa: F401, E402
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
    Context,
    Dialer,
    Listener,
    Pipe,
    Message,
)

# Import shared types from base
from pynng._base import PipeEvent, PipeEventStream  # noqa: F401, E402

# Import shared exceptions (same for v1 and v2)
from pynng.exceptions import (  # noqa: F401, E402
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
    from pynng.service import Rep0Service, Request  # noqa: F401, E402
except ImportError:
    pass

# Import TLS config (same TLS primitives, applied at endpoint level in v2)
from pynng.tls import TLSConfig  # noqa: F401, E402
