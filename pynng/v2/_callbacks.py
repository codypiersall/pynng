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

from __future__ import annotations

from collections.abc import Callable
import logging
from typing import TYPE_CHECKING, Protocol, TypeAlias, TypeVar, cast

from pynng._aio import _aio_map
from pynng._base import _handle_pipe_event
from pynng._nng_v2 import ffi, lib

if TYPE_CHECKING:
    import cffi

    from pynng import _base, _nng_v2

    _CallbackFn: TypeAlias = (
        Callable[[cffi.FFI.CData], None]
        | Callable[[_nng_v2.nng_pipe, int, cffi.FFI.CData], None]
    )

logger = logging.getLogger(__name__)
_F = TypeVar("_F", bound="_CallbackFn")


class _ExternDecorator(Protocol):
    def __call__(self, fn: _F, /) -> _F: ...


_def_extern: Callable[[], _ExternDecorator] = getattr(ffi, "def_extern")
_ffi_error: type[BaseException] = getattr(ffi, "error", RuntimeError)


@_def_extern()
def _async_complete(void_p: cffi.FFI.CData) -> None:
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


@_def_extern()
def _nng_pipe_cb(lib_pipe: _nng_v2.nng_pipe, event: int, arg: cffi.FFI.CData) -> None:
    """
    Pipe notification callback for v2 sockets.

    Dispatches to the Socket's pipe callback lists, identical to the v1
    version but using the v2 ffi for handle resolution.
    """
    logger.debug(f"v2 pipe callback event {event}")

    try:
        sock = cast("_base.Socket", ffi.from_handle(arg))
    except (RuntimeError, ValueError, _ffi_error):
        logger.info(
            "v2 pipe callback fired with invalid handle (socket likely GC'd); ignoring"
        )
        return

    _handle_pipe_event(sock, lib_pipe, event, lib)
