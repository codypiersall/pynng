"""
v2-specific CFFI callbacks for async I/O and pipe notifications.

These are structurally identical to the v1 callbacks in ``pynng._aio`` and
``pynng.nng``, but are bound to the v2 CFFI module (``pynng._nng_v2``).

The callbacks share the same Python-side dispatch data structures as v1:

- ``_aio_map`` from ``pynng._aio`` (keyed by ``id()``,
  so v1/v2 AIO objects cannot collide).
- ``_active_handles`` from ``pynng._base`` (keyed
  by ``(version_tag, socket_id)`` tuples, preventing v1/v2 collision).
"""

import logging

from pynng._nng_v2 import ffi, lib
from pynng._aio import _aio_map
from pynng._base import (
    _handle_pipe_event,
)

logger = logging.getLogger(__name__)


@ffi.def_extern()
def _async_complete(void_p):
    """
    Callback provided to nng_aio_alloc for v2 async operations.

    Looks up and invokes the rescheduler stored in ``_aio_map``.
    """
    assert isinstance(void_p, ffi.CData)
    id_val = int(ffi.cast("size_t", void_p))

    rescheduler = _aio_map.pop(id_val, None)
    if rescheduler is None:
        return
    rescheduler()


@ffi.def_extern()
def _nng_pipe_cb(lib_pipe, event, arg):
    """
    Pipe notification callback for v2 sockets.

    Dispatches to the Socket's pipe callback lists, identical to the v1
    version but using the v2 ffi for handle resolution.
    """
    logger.debug("v2 pipe callback event {}".format(event))

    try:
        sock = ffi.from_handle(arg)
    except (RuntimeError, ValueError, ffi.error):
        logger.info(
            "v2 pipe callback fired with invalid handle (socket likely GC'd); ignoring"
        )
        return

    _handle_pipe_event(sock, lib_pipe, event, lib)
