"""
Helpers for AIO functions
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Coroutine
import os
import threading
from types import TracebackType
from typing import (
    TYPE_CHECKING,
    NoReturn,
    Protocol,
    TypeAlias,
    TypeVar,
    cast,
)
import weakref

import sniffio

from ._finalized import is_nng_finalized as _is_nng_finalized
from ._nng import ffi, lib
from .exceptions import check_err

if TYPE_CHECKING:
    import cffi

    from . import _base, _nng, _nng_v2

    _NngLib: TypeAlias = _nng._Lib | _nng_v2._Lib
    _NngAio: TypeAlias = _nng.nng_aio | _nng_v2.nng_aio
    _NngMsg: TypeAlias = _nng.nng_msg | _nng_v2.nng_msg
    _NngSocket: TypeAlias = _nng.nng_socket | _nng_v2.nng_socket
    _NngCtx: TypeAlias = _nng.nng_ctx | _nng_v2.nng_ctx
    _MpscQueue: TypeAlias = _nng.pynng_mpsc_queue_t | _nng_v2.pynng_mpsc_queue_t
    _AioEntry: TypeAlias = _nng.pynng_aio_entry_t | _nng_v2.pynng_aio_entry_t
    _AioTargetHandle: TypeAlias = _NngSocket | _NngCtx
    _AioCallbackFn: TypeAlias = Callable[[cffi.FFI.CData], None]

_F = TypeVar("_F", bound="_AioCallbackFn")
_AIOHelperSelfT = TypeVar("_AIOHelperSelfT", bound="AIOHelper")
_DeviceAIOSelfT = TypeVar("_DeviceAIOSelfT", bound="DeviceAIO")


class _ExternDecorator(Protocol):
    def __call__(self, fn: _F, /) -> _F: ...


class _AioLibProtocol(Protocol):
    NNG_ECANCELED: int
    pynng_native_aio_complete: _AioCallbackFn
    _async_complete: _AioCallbackFn

    def pynng_mpsc_queue_new(self, wake_fd: int) -> _MpscQueue: ...
    def pynng_mpsc_queue_close(self, q: _MpscQueue | cffi.FFI.CData) -> None: ...
    def pynng_mpsc_queue_free(self, q: _MpscQueue | cffi.FFI.CData) -> None: ...
    def pynng_mpsc_drain_batch(
        self,
        q: _MpscQueue | cffi.FFI.CData,
        out_slots: cffi.FFI.CData,
        max_slots: int,
    ) -> int: ...
    def pynng_aio_entry_new(
        self,
        aio: _NngAio | cffi.FFI.CData,
        slot_id: int,
        q: _MpscQueue | cffi.FFI.CData,
    ) -> _AioEntry: ...
    def pynng_aio_entry_free(self, entry: _AioEntry) -> None: ...
    def pynng_aio_entry_set_slot_id(self, entry: _AioEntry, slot_id: int) -> None: ...
    def pynng_aio_entry_is_idle(self, entry: _AioEntry) -> int: ...
    def nng_aio_alloc(
        self,
        aio_p: cffi.FFI.CData,
        cb: _AioCallbackFn,
        arg: _AioEntry | cffi.FFI.CData,
    ) -> int: ...
    def nng_aio_free(self, aio: _NngAio) -> None: ...
    def nng_aio_cancel(self, aio: _NngAio) -> None: ...
    def nng_aio_wait(self, aio: _NngAio) -> None: ...
    def nng_aio_result(self, aio: _NngAio) -> int: ...
    def nng_aio_get_msg(self, aio: _NngAio) -> _NngMsg: ...
    def nng_aio_set_msg(self, aio: _NngAio, msg: _NngMsg | cffi.FFI.CData) -> None: ...
    def nng_msg_alloc(self, msg_p: cffi.FFI.CData, size: int) -> int: ...
    def nng_msg_append(
        self, msg: _NngMsg, data: bytes | cffi.FFI.CData, size: int
    ) -> int: ...
    def nng_msg_free(self, msg: _NngMsg) -> None: ...
    def nng_recv_aio(self, s: _AioTargetHandle, aio: _NngAio) -> int: ...
    def nng_send_aio(self, s: _AioTargetHandle, aio: _NngAio) -> int: ...
    def nng_ctx_recv(self, ctx: _AioTargetHandle, aio: _NngAio) -> int: ...
    def nng_ctx_send(self, ctx: _AioTargetHandle, aio: _NngAio) -> int: ...


# global variable for mapping asynchronous operations with the Python data
# assocated with them.  Key is id(obj), value is obj
# No lock guards it: AIOHelper.__del__ updates it, and a finalizer can run
# while its thread holds any lock. Each access is one dict operation, which is
# atomic with and without the GIL.
_aio_map: dict[int, Callable[[], None]] = {}

# Marks the threads inside _base._device_section(), which holds the device lock.
_device_section_thread = threading.local()


def _in_device_section() -> bool:
    """Return True if this thread can hold the device lock.

    A finalizer can run inside a device section, so a finalizer that needs
    the lock must hand that work to another thread when this returns True.
    """
    return getattr(_device_section_thread, "depth", 0) > 0


def _make_notify_cb(
    engine_ref: weakref.ReferenceType[MPSCAIOEngine],
) -> Callable[[], None]:
    def _cb() -> None:
        engine = engine_ref()
        if engine is not None:
            engine._on_notify()

    return _cb


class MPSCAIOEngine:
    """Wait-free C11 MPSC intrusive queue engine for asyncio event loops.

    Routes nng aio completions directly through Dmitry Vyukov's wait-free MPSC
    queue in native C without acquiring the Python GIL on nng worker threads,
    notifying the asyncio loop via a non-blocking wake pipe.
    """

    __slots__ = (
        "_loop_ref",
        "_lib",
        "_ffi",
        "_closed",
        "_read_fd",
        "_write_fd",
        "_queue",
        "_slots",
        "_slot_counter",
        "_batch_size",
        "_batch_buf",
        "__weakref__",
    )

    _loop_engines: weakref.WeakKeyDictionary[
        asyncio.AbstractEventLoop, dict[int, MPSCAIOEngine]
    ] = weakref.WeakKeyDictionary()
    _lock = threading.Lock()

    def __init__(
        self, loop: asyncio.AbstractEventLoop, lib: _NngLib, ffi: cffi.FFI
    ) -> None:
        self._loop_ref = weakref.ref(loop)
        self._lib = lib
        self._ffi = ffi
        self._closed = False
        self._read_fd = -1
        self._write_fd = -1
        self._queue: _MpscQueue | cffi.FFI.CData = ffi.NULL
        aio_lib = cast(_AioLibProtocol, lib)
        r, w = os.pipe()
        try:
            os.set_blocking(r, False)
            os.set_blocking(w, False)
            self._read_fd = r
            self._write_fd = w
            self._queue = aio_lib.pynng_mpsc_queue_new(w)
            self._slots: dict[int, asyncio.Future[None]] = {}
            self._slot_counter = 0
            self._batch_size = 256
            self._batch_buf = ffi.new(f"uintptr_t[{self._batch_size}]")
            loop.add_reader(self._read_fd, _make_notify_cb(weakref.ref(self)))
        except BaseException:
            self.close()
            if self._queue != ffi.NULL:
                aio_lib.pynng_mpsc_queue_free(self._queue)
                self._queue = ffi.NULL
            raise

    @property
    def _loop(self) -> asyncio.AbstractEventLoop | None:
        return self._loop_ref()

    @classmethod
    def get_for_loop(
        cls,
        loop: asyncio.AbstractEventLoop | None,
        lib: _NngLib,
        ffi: cffi.FFI,
    ) -> MPSCAIOEngine | None:
        if loop is None or loop.is_closed() or not hasattr(loop, "add_reader"):
            return None
        with cls._lock:
            # Opportunistically close engines belonging to closed event loops
            for existing_loop, existing_by_lib in list(cls._loop_engines.items()):
                if existing_loop.is_closed():
                    for eng in existing_by_lib.values():
                        eng.close()
                    cls._loop_engines.pop(existing_loop, None)

            by_lib = cls._loop_engines.get(loop)
            if by_lib is None:
                by_lib = {}
                cls._loop_engines[loop] = by_lib
            lib_key = id(lib)
            engine = by_lib.get(lib_key)
            if engine is None or engine._closed:
                try:
                    engine = cls(loop, lib, ffi)
                    by_lib[lib_key] = engine
                except (AttributeError, NotImplementedError, OSError, RuntimeError):
                    return None
            return engine

    def _on_notify(self) -> None:
        if self._closed or self._read_fd < 0:
            return
        try:
            os.read(self._read_fd, 65536)
        except (BlockingIOError, OSError):
            pass
        if self._queue == self._ffi.NULL:
            return
        aio_lib = cast(_AioLibProtocol, self._lib)
        while True:
            count = aio_lib.pynng_mpsc_drain_batch(
                self._queue, self._batch_buf, self._batch_size
            )
            if count == 0:
                break
            for i in range(count):
                slot_id = int(self._batch_buf[i])
                fut = self._slots.pop(slot_id, None)
                if fut is not None and not fut.done():
                    fut.set_result(None)

    def register(self, fut: asyncio.Future[None]) -> int:
        while True:
            self._slot_counter = (self._slot_counter + 1) & 0x7FFFFFFF
            if self._slot_counter == 0:
                self._slot_counter = 1
            if self._slot_counter not in self._slots:
                break
        slot_id = self._slot_counter
        self._slots[slot_id] = fut
        return slot_id

    def unregister(self, slot_id: int) -> None:
        self._slots.pop(slot_id, None)

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._queue != self._ffi.NULL and hasattr(
            self._lib, "pynng_mpsc_queue_close"
        ):
            cast(_AioLibProtocol, self._lib).pynng_mpsc_queue_close(self._queue)
        loop = self._loop_ref() if hasattr(self, "_loop_ref") else None
        if self._read_fd >= 0:
            if loop is not None and not loop.is_closed():
                try:
                    loop.remove_reader(self._read_fd)
                except (RuntimeError, KeyError, ValueError, AttributeError, OSError):
                    pass
            try:
                os.close(self._read_fd)
            except OSError:
                pass
            self._read_fd = -1

        if self._write_fd >= 0:
            try:
                os.close(self._write_fd)
            except OSError:
                pass
            self._write_fd = -1

        if hasattr(self, "_slots"):
            for fut in list(self._slots.values()):
                if not fut.done():
                    try:
                        fut.cancel()
                    except RuntimeError:
                        pass
            self._slots.clear()

    def __del__(self) -> None:
        try:
            self.close()
            if getattr(self, "_queue", None) not in (None, self._ffi.NULL):
                cast(_AioLibProtocol, self._lib).pynng_mpsc_queue_free(self._queue)
                self._queue = self._ffi.NULL
        except Exception:
            pass


_def_extern: Callable[[], _ExternDecorator] = getattr(ffi, "def_extern")


@_def_extern()
def _async_complete(void_p: cffi.FFI.CData) -> None:
    """
    This is the callback provided to nng_aio_* functions which completes the
    Python future argument passed to it.  It schedules _set_future_finished
    to run to complete the future associated with the event.
    """
    # this is not a public interface, so asserting invariants is good.
    assert isinstance(void_p, ffi.CData)
    id_val = int(ffi.cast("size_t", void_p))

    rescheduler = _aio_map.pop(id_val, None)
    if rescheduler is None:
        return
    rescheduler()


def asyncio_helper(
    aio: AIOHelper | DeviceAIO,
) -> tuple[Coroutine[object, None, None], Callable[[], None]]:
    """
    Returns a callable that will be passed to _async_complete.  The callable is
    responsible for rescheduling the event loop

    """
    _lib = aio._lib
    _ffi = aio._ffi
    aio_lib = cast(_AioLibProtocol, _lib)
    loop = asyncio.get_running_loop()
    fut: asyncio.Future[None] = loop.create_future()

    async def wait_for_aio() -> None:
        assert aio.aio is not None
        already_called_nng_aio_cancel = False
        while True:
            try:
                await asyncio.shield(fut)
            except asyncio.CancelledError:
                if not already_called_nng_aio_cancel:
                    aio_lib.nng_aio_cancel(aio.aio)
                    already_called_nng_aio_cancel = True
            else:
                break
        err = aio_lib.nng_aio_result(aio.aio)
        if already_called_nng_aio_cancel or err == _lib.NNG_ECANCELED:
            raise asyncio.CancelledError
        check_err(err, lib=_lib, ffi=_ffi)

    def _set_future_finished(fut: asyncio.Future[None]) -> None:
        if not fut.done():
            fut.set_result(None)

    def rescheduler() -> None:
        loop.call_soon_threadsafe(_set_future_finished, fut)

    return wait_for_aio(), rescheduler


def trio_helper(
    aio: AIOHelper | DeviceAIO,
) -> tuple[Coroutine[object, None, None], Callable[[], None]]:
    # Record the info needed to get back into this task
    import trio

    _lib = aio._lib
    _ffi = aio._ffi
    aio_lib = cast(_AioLibProtocol, _lib)

    token = trio.lowlevel.current_trio_token()
    task = trio.lowlevel.current_task()

    def resumer() -> None:
        token.run_sync_soon(trio.lowlevel.reschedule, task)

    async def wait_for_aio() -> None:
        assert aio.aio is not None
        # Machinery to handle Trio cancellation, and convert it into nng cancellation
        raise_cancel_fn: Callable[[], NoReturn] | None = None

        def abort_fn(
            raise_cancel_arg: Callable[[], NoReturn],
        ) -> trio.lowlevel.Abort:
            assert aio.aio is not None
            # This function is called if Trio wants to cancel the operation.
            # First, ask nng to cancel the operation.
            aio_lib.nng_aio_cancel(aio.aio)
            # nng cancellation doesn't happen immediately, so we need to save the raise_cancel function
            # into the enclosing scope to call it later, after we find out if the cancellation actually happened.
            nonlocal raise_cancel_fn
            raise_cancel_fn = raise_cancel_arg
            # And then tell Trio that we weren't able to cancel the operation immediately, so it should keep
            # waiting.
            return trio.lowlevel.Abort.FAILED

        # Put the Trio task to sleep.
        await trio.lowlevel.wait_task_rescheduled(abort_fn)

        err = aio_lib.nng_aio_result(aio.aio)
        if err == _lib.NNG_ECANCELED and raise_cancel_fn is not None:
            # This operation was successfully cancelled.
            # Call the function Trio gave us, which raises the proper Trio cancellation exception
            raise_cancel_fn()
        check_err(err, lib=_lib, ffi=_ffi)

    return wait_for_aio(), resumer


class AIOHelper:
    """
    Handles the nng_aio operations for the correct event loop.  This class
    mostly exists to easily keep up with resources and, to some extent,
    abstract away different event loops; event loop implementations are now
    punted into the module level helper functions.  Theoretically it should be
    somewhat straightforward to support different event loops by adding a key
    to the ``_aio_helper_map`` and supplying a helper function.
    """

    # global dict that maps {event loop: helper_function}.  The helper function
    # takes one argument (an AIOHelper instance) and returns an (awaitable,
    # callback_function) tuple.  The callback_function will be called (with no
    # argumnts provided) to mark the awaitable ready.
    _aio_helper_map: dict[
        str,
        Callable[
            [AIOHelper | DeviceAIO],
            tuple[Coroutine[object, None, None], Callable[[], None]],
        ],
    ] = {
        "asyncio": asyncio_helper,
        "trio": trio_helper,
    }

    __slots__ = (
        "aio",
        "_mpsc_engine",
        "_aio_entry",
        "_current_slot",
        "_current_fut",
        "_sending",
        "cb_arg",
        "awaitable",
        "obj",
        "_lib",
        "_ffi",
        "_nng_obj",
        "_lib_arecv",
        "_lib_asend",
        "async_backend",
    )

    def __init__(
        self,
        obj: _base.Socket | _base.Context,
        async_backend: str | None,
        _lib: _NngLib | None = None,
        _ffi: cffi.FFI | None = None,
        *,
        _use_mpsc: bool = True,
    ) -> None:
        # set to None now so we can know if we need to free it later
        # This should be at the top of __init__ so that __del__ doesn't raise
        # an unexpected AttributeError if something funky happens
        self.aio: _NngAio | None = None
        self._mpsc_engine: MPSCAIOEngine | None = None
        self._aio_entry: _AioEntry | None = None
        self._current_slot: int | None = None
        self._current_fut: asyncio.Future[None] | None = None
        self._sending = False
        self.cb_arg: Callable[[], None] | None = None
        self.awaitable: Coroutine[object, None, None] | None = None

        # Resolve lib/ffi from the object if not explicitly provided
        from . import _base

        if _lib is None or _ffi is None:
            if isinstance(obj, _base.Socket):
                if _lib is None:
                    _lib = obj._lib
                if _ffi is None:
                    _ffi = obj._ffi
            elif isinstance(obj, _base.Context):
                if _lib is None:
                    _lib = obj._socket._lib
                if _ffi is None:
                    _ffi = obj._socket._ffi
            else:
                # Fallback to v1
                if _lib is None:
                    _lib = lib
                if _ffi is None:
                    _ffi = ffi

        assert _lib is not None
        assert _ffi is not None
        self._lib: _NngLib = _lib
        self._ffi: cffi.FFI = _ffi
        aio_lib = cast(_AioLibProtocol, _lib)

        # this is not a public interface, let's make some assertions
        assert isinstance(obj, (_base.Socket, _base.Context))
        # we need to choose the correct nng lib functions based on the type of
        # object we've been passed; but really, all the logic is identical
        self._nng_obj: _AioTargetHandle
        self._lib_arecv: Callable[[_AioTargetHandle, _NngAio], int]
        self._lib_asend: Callable[[_AioTargetHandle, _NngAio], int]
        if isinstance(obj, _base.Socket):
            self._nng_obj = obj.socket
            # Use _aio_recv_fn / _aio_send_fn properties if available,
            # otherwise fall back to v1 function names
            if getattr(obj, "_aio_recv_fn", None) is not None:
                self._lib_arecv = cast(
                    "Callable[[_AioTargetHandle, _NngAio], int]", obj._aio_recv_fn
                )
                self._lib_asend = cast(
                    "Callable[[_AioTargetHandle, _NngAio], int]", obj._aio_send_fn
                )
            else:
                self._lib_arecv = aio_lib.nng_recv_aio
                self._lib_asend = aio_lib.nng_send_aio
        else:
            self._nng_obj = obj.context
            self._lib_arecv = aio_lib.nng_ctx_recv
            self._lib_asend = aio_lib.nng_ctx_send
        self.obj = obj
        if async_backend is None:
            async_backend = sniffio.current_async_library()
        if async_backend not in self._aio_helper_map:
            raise ValueError(
                f"The async backend {async_backend} is not currently supported."
            )
        self.async_backend = async_backend

        # Attempt to use wait-free MPSC queue under asyncio
        if _use_mpsc and async_backend == "asyncio":
            try:
                loop = asyncio.get_running_loop()
                if hasattr(_lib, "pynng_native_aio_complete"):
                    self._mpsc_engine = MPSCAIOEngine.get_for_loop(loop, _lib, _ffi)
            except RuntimeError:
                pass

        if self._mpsc_engine is not None:
            self._aio_entry = aio_lib.pynng_aio_entry_new(
                _ffi.NULL, 0, self._mpsc_engine._queue
            )
            aio_p = _ffi.new("nng_aio **")
            check_err(
                aio_lib.nng_aio_alloc(
                    aio_p, aio_lib.pynng_native_aio_complete, self._aio_entry
                ),
                lib=_lib,
                ffi=_ffi,
            )
            self.aio = cast("_NngAio", aio_p[0])
        else:
            self.awaitable, self.cb_arg = self._aio_helper_map[async_backend](self)
            aio_p = _ffi.new("nng_aio **")
            _aio_map[id(self.cb_arg)] = self.cb_arg
            idarg = id(self.cb_arg)
            as_void = _ffi.cast("void *", idarg)
            try:
                check_err(
                    aio_lib.nng_aio_alloc(aio_p, aio_lib._async_complete, as_void),
                    lib=_lib,
                    ffi=_ffi,
                )
            except BaseException:
                _aio_map.pop(idarg, None)
                raise
            self.aio = cast("_NngAio", aio_p[0])

    def is_valid_for_current_loop(self) -> bool:
        engine = self._mpsc_engine
        if (
            engine is None
            or engine._closed
            or self.aio is None
            or self._aio_entry is None
        ):
            return False
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return False
        return (
            engine._loop is loop
            and not loop.is_closed()
            and self._current_slot is None
            and not self._sending
            and bool(
                cast(_AioLibProtocol, self._lib).pynng_aio_entry_is_idle(
                    self._aio_entry
                )
            )
        )

    def _prepare_aio(self) -> None:
        if self._mpsc_engine is not None:
            loop = self._mpsc_engine._loop
            if loop is None or loop.is_closed():
                raise RuntimeError("Event loop is closed")
            assert self._aio_entry is not None
            fut: asyncio.Future[None] = loop.create_future()
            slot = self._mpsc_engine.register(fut)
            self._current_slot = slot
            self._current_fut = fut
            cast(_AioLibProtocol, self._lib).pynng_aio_entry_set_slot_id(
                self._aio_entry, slot
            )

    def _cleanup_prepared_aio(self) -> None:
        if self._mpsc_engine is not None:
            if self._current_slot is not None:
                self._mpsc_engine.unregister(self._current_slot)
                self._current_slot = None
            self._current_fut = None
            if self._aio_entry is not None:
                cast(_AioLibProtocol, self._lib).pynng_aio_entry_set_slot_id(
                    self._aio_entry, 0
                )

    async def _wait_for_aio(self) -> None:
        if self._mpsc_engine is not None:
            fut = self._current_fut
            assert fut is not None
            assert self.aio is not None
            _lib = self._lib
            aio_lib = cast(_AioLibProtocol, _lib)
            already_cancelled = False
            try:
                while True:
                    try:
                        await asyncio.shield(fut)
                    except asyncio.CancelledError:
                        if not already_cancelled:
                            aio_lib.nng_aio_cancel(self.aio)
                            already_cancelled = True
                    else:
                        break
            finally:
                if self._current_slot is not None:
                    self._mpsc_engine.unregister(self._current_slot)
                    self._current_slot = None
                self._current_fut = None
                if self._aio_entry is not None:
                    aio_lib.pynng_aio_entry_set_slot_id(self._aio_entry, 0)
            err = aio_lib.nng_aio_result(self.aio)
            if already_cancelled or err == _lib.NNG_ECANCELED:
                raise asyncio.CancelledError
            check_err(err, lib=_lib, ffi=self._ffi)
        else:
            assert self.awaitable is not None
            await self.awaitable

    async def arecv(self) -> bytes:
        msg = await self.arecv_msg()
        return msg.bytes

    async def arecv_msg(self) -> _base.Message:
        assert self.aio is not None
        _lib = self._lib
        _ffi = self._ffi
        aio_lib = cast(_AioLibProtocol, _lib)
        self._prepare_aio()
        try:
            check_err(self._lib_arecv(self._nng_obj, self.aio), lib=_lib, ffi=_ffi)
        except BaseException:
            self._cleanup_prepared_aio()
            raise
        try:
            await self._wait_for_aio()
        except BaseException:
            msg = aio_lib.nng_aio_get_msg(self.aio)
            if cast("cffi.FFI.CData", msg) != _ffi.NULL:
                aio_lib.nng_aio_set_msg(self.aio, _ffi.NULL)
                aio_lib.nng_msg_free(msg)
            raise
        check_err(aio_lib.nng_aio_result(self.aio), lib=_lib, ffi=_ffi)
        msg = aio_lib.nng_aio_get_msg(self.aio)
        aio_lib.nng_aio_set_msg(self.aio, _ffi.NULL)
        from ._base import Context, Message, Socket

        # Use the socket's message class if available
        msg_cls: type[Message] = Message
        if isinstance(self.obj, Socket) and self.obj._message_class is not None:
            msg_cls = self.obj._message_class
        elif (
            isinstance(self.obj, Context)
            and self.obj._socket._message_class is not None
        ):
            msg_cls = self.obj._socket._message_class
        return msg_cls(msg, _lib=_lib, _ffi=_ffi)

    async def asend(self, data: _base.ReadableBuffer) -> None:
        assert self.aio is not None
        _lib = self._lib
        _ffi = self._ffi
        aio_lib = cast(_AioLibProtocol, _lib)
        msg_p = _ffi.new("nng_msg **")
        check_err(aio_lib.nng_msg_alloc(msg_p, 0), lib=_lib, ffi=_ffi)
        msg = cast("_NngMsg", msg_p[0])
        try:
            buf: bytes | cffi.FFI.CData
            if isinstance(data, bytes):
                buf = data
            else:
                buf = _ffi.from_buffer(data)
            check_err(aio_lib.nng_msg_append(msg, buf, len(data)), lib=_lib, ffi=_ffi)
            self._prepare_aio()
            aio_lib.nng_aio_set_msg(self.aio, msg)
            self._sending = True
            check_err(self._lib_asend(self._nng_obj, self.aio), lib=_lib, ffi=_ffi)
        except BaseException:
            self._sending = False
            self._cleanup_prepared_aio()
            aio_lib.nng_aio_set_msg(self.aio, _ffi.NULL)
            aio_lib.nng_msg_free(msg)
            raise
        try:
            await self._wait_for_aio()
        except BaseException:
            leftover = aio_lib.nng_aio_get_msg(self.aio)
            if cast("cffi.FFI.CData", leftover) != _ffi.NULL:
                aio_lib.nng_aio_set_msg(self.aio, _ffi.NULL)
                aio_lib.nng_msg_free(leftover)
            raise
        finally:
            self._sending = False

    async def asend_msg(self, msg: _base.Message) -> None:
        """
        Asynchronously send a Message

        """
        assert self.aio is not None
        _lib = self._lib
        _ffi = self._ffi
        aio_lib = cast(_AioLibProtocol, _lib)
        msg._ensure_can_send()
        self._prepare_aio()
        aio_lib.nng_aio_set_msg(self.aio, msg._nng_msg)
        msg._mem_freed = True
        self._sending = True
        try:
            check_err(self._lib_asend(self._nng_obj, self.aio), lib=_lib, ffi=_ffi)
        except BaseException:
            self._sending = False
            self._cleanup_prepared_aio()
            aio_lib.nng_aio_set_msg(self.aio, _ffi.NULL)
            aio_lib.nng_msg_free(msg._nng_msg)
            raise
        try:
            await self._wait_for_aio()
        except BaseException:
            leftover = aio_lib.nng_aio_get_msg(self.aio)
            if cast("cffi.FFI.CData", leftover) != _ffi.NULL:
                aio_lib.nng_aio_set_msg(self.aio, _ffi.NULL)
                aio_lib.nng_msg_free(leftover)
            raise
        finally:
            self._sending = False

    def _free(self) -> None:
        """
        Free resources allocated with nng
        """
        try:
            if _is_nng_finalized():
                self.aio = None
                self._aio_entry = None
                if self.cb_arg is not None:
                    _aio_map.pop(id(self.cb_arg), None)
                return
        except (ImportError, AttributeError):
            pass

        if self._current_slot is not None and self._mpsc_engine is not None:
            self._mpsc_engine.unregister(self._current_slot)
            self._current_slot = None
        self._current_fut = None

        if self.aio is not None:
            _lib = self._lib
            _ffi = self._ffi
            aio_lib = cast(_AioLibProtocol, _lib)
            # Cancel in-flight AIO before freeing to prevent deadlock during GC.
            aio_lib.nng_aio_cancel(self.aio)
            aio_lib.nng_aio_wait(self.aio)
            if self._sending:
                leftover = aio_lib.nng_aio_get_msg(self.aio)
                if cast("cffi.FFI.CData", leftover) != _ffi.NULL:
                    aio_lib.nng_aio_set_msg(self.aio, _ffi.NULL)
                    aio_lib.nng_msg_free(leftover)
                self._sending = False
            aio_lib.nng_aio_free(self.aio)
            self.aio = None

        if self._aio_entry is not None:
            cast(_AioLibProtocol, self._lib).pynng_aio_entry_free(self._aio_entry)
            self._aio_entry = None

        if self._mpsc_engine is not None:
            loop = self._mpsc_engine._loop
            if loop is None or loop.is_closed():
                self._mpsc_engine.close()

        if self.cb_arg is not None:
            _aio_map.pop(id(self.cb_arg), None)
            self.cb_arg = None

        if self.awaitable is not None:
            try:
                self.awaitable.close()
            except (RuntimeError, AttributeError):
                pass
            self.awaitable = None

    def __enter__(self: _AIOHelperSelfT) -> _AIOHelperSelfT:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        self._free()

    def __del__(self) -> None:
        self._free()


class DeviceAIO:
    """Handles an asynchronous nng_device_aio operation for the correct event loop."""

    __slots__ = (
        "aio",
        "_mpsc_engine",
        "_aio_entry",
        "_current_slot",
        "cb_arg",
        "awaitable",
        "s1",
        "s2",
        "_lib",
        "_ffi",
        "_sock1",
        "_sock2",
        "_owners",
        "_stop_device",
    )

    def __init__(
        self,
        s1: _base.Socket | _NngSocket | cffi.FFI.CData,
        s2: _base.Socket | _NngSocket | cffi.FFI.CData | None = None,
        async_backend: str | None = None,
        *,
        _use_mpsc: bool = True,
        _default_lib: _NngLib = lib,
        _default_ffi: cffi.FFI = ffi,
    ) -> None:
        self.aio: _NngAio | None = None
        self._mpsc_engine: MPSCAIOEngine | None = None
        self._aio_entry: _AioEntry | None = None
        self._current_slot: int | None = None
        self.cb_arg: Callable[[], None] | None = None
        self.awaitable: Coroutine[object, None, None] | None = None
        self.s1 = s1
        self.s2 = s2
        from . import _base

        # _free() can run at interpreter shutdown, when importing fails.
        self._stop_device = _base._stop_device
        self._lib, self._ffi, sock1, sock2 = _base._device_sockets(
            s1, s2, _default_lib, _default_ffi
        )
        self._owners = tuple(s for s in (s1, s2) if isinstance(s, _base.Socket))
        self._sock1 = sock1
        self._sock2 = sock2
        aio_lib = cast(_AioLibProtocol, self._lib)

        if async_backend is None:
            if isinstance(s1, _base.Socket) and s1._async_backend is not None:
                async_backend = s1._async_backend
            else:
                async_backend = sniffio.current_async_library()
        if async_backend not in AIOHelper._aio_helper_map:
            raise ValueError(
                f"The async backend {async_backend} is not currently supported."
            )

        if _use_mpsc and async_backend == "asyncio":
            try:
                loop = asyncio.get_running_loop()
                if hasattr(self._lib, "pynng_native_aio_complete"):
                    self._mpsc_engine = MPSCAIOEngine.get_for_loop(
                        loop, self._lib, self._ffi
                    )
            except RuntimeError:
                pass

        if self._mpsc_engine is not None:
            self._aio_entry = aio_lib.pynng_aio_entry_new(
                self._ffi.NULL, 0, self._mpsc_engine._queue
            )
            aio_p = self._ffi.new("nng_aio **")
            check_err(
                aio_lib.nng_aio_alloc(
                    aio_p, aio_lib.pynng_native_aio_complete, self._aio_entry
                ),
                lib=self._lib,
                ffi=self._ffi,
            )
            self.aio = cast("_NngAio", aio_p[0])
        else:
            self.awaitable, self.cb_arg = AIOHelper._aio_helper_map[async_backend](self)
            aio_p = self._ffi.new("nng_aio **")
            _aio_map[id(self.cb_arg)] = self.cb_arg
            idarg = id(self.cb_arg)
            as_void = self._ffi.cast("void *", idarg)
            try:
                check_err(
                    aio_lib.nng_aio_alloc(aio_p, aio_lib._async_complete, as_void),
                    lib=self._lib,
                    ffi=self._ffi,
                )
            except BaseException:
                _aio_map.pop(idarg, None)
                raise
            self.aio = cast("_NngAio", aio_p[0])

    async def run(self) -> None:
        from . import _base

        try:
            assert self.aio is not None
            aio_lib = cast(_AioLibProtocol, self._lib)
            if self._mpsc_engine is not None:
                loop = self._mpsc_engine._loop
                if loop is None or loop.is_closed():
                    raise RuntimeError("Event loop is closed")
                assert self._aio_entry is not None
                fut: asyncio.Future[None] = loop.create_future()
                slot = self._mpsc_engine.register(fut)
                self._current_slot = slot
                aio_lib.pynng_aio_entry_set_slot_id(self._aio_entry, slot)
                _base._start_device(
                    self._owners, self._lib, self.aio, self._sock1, self._sock2
                )
                _lib = self._lib
                already_cancelled = False
                try:
                    while True:
                        try:
                            await asyncio.shield(fut)
                        except asyncio.CancelledError:
                            if not already_cancelled:
                                aio_lib.nng_aio_cancel(self.aio)
                                already_cancelled = True
                        else:
                            break
                finally:
                    if self._current_slot is not None:
                        self._mpsc_engine.unregister(self._current_slot)
                        self._current_slot = None
                    if self._aio_entry is not None:
                        aio_lib.pynng_aio_entry_set_slot_id(self._aio_entry, 0)
                err = aio_lib.nng_aio_result(self.aio)
                if already_cancelled or err == _lib.NNG_ECANCELED:
                    raise asyncio.CancelledError
                check_err(err, lib=_lib, ffi=self._ffi)
            else:
                assert self.awaitable is not None
                _base._start_device(
                    self._owners, self._lib, self.aio, self._sock1, self._sock2
                )
                await self.awaitable
        finally:
            self._free()

    def _free(self) -> None:
        try:
            if _is_nng_finalized():
                self.aio = None
                self._aio_entry = None
                if self.cb_arg is not None:
                    _aio_map.pop(id(self.cb_arg), None)
                return
        except (ImportError, AttributeError):
            pass

        if self._current_slot is not None and self._mpsc_engine is not None:
            self._mpsc_engine.unregister(self._current_slot)
            self._current_slot = None

        if self.aio is not None:
            aio_lib = cast(_AioLibProtocol, self._lib)
            aio_lib.nng_aio_cancel(self.aio)
            aio_lib.nng_aio_wait(self.aio)
            self._stop_device(self._owners, self.aio)
            aio_lib.nng_aio_free(self.aio)
            self.aio = None

        if self._aio_entry is not None:
            cast(_AioLibProtocol, self._lib).pynng_aio_entry_free(self._aio_entry)
            self._aio_entry = None

        if self._mpsc_engine is not None:
            loop = self._mpsc_engine._loop
            if loop is None or loop.is_closed():
                self._mpsc_engine.close()

        if self.cb_arg is not None:
            _aio_map.pop(id(self.cb_arg), None)
            self.cb_arg = None

        if self.awaitable is not None:
            try:
                self.awaitable.close()
            except (RuntimeError, AttributeError):
                pass
            self.awaitable = None

    def __enter__(self: _DeviceAIOSelfT) -> _DeviceAIOSelfT:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        self._free()

    def __del__(self) -> None:
        if _in_device_section():
            # _free() takes the device lock, which this thread can hold.
            threading.Thread(target=self._free, name="pynng-device-free").start()
        else:
            self._free()
