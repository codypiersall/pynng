"""
Helpers for AIO functions
"""

import asyncio
import os
import threading
import weakref

import sniffio

from ._nng import ffi, lib
from .exceptions import check_err
from ._finalized import is_nng_finalized as _is_nng_finalized

# global variable for mapping asynchronous operations with the Python data
# assocated with them.  Key is id(obj), value is obj
# No lock guards it: AIOHelper.__del__ updates it, and a finalizer can run
# while its thread holds any lock. Each access is one dict operation, which is
# atomic with and without the GIL.
_aio_map = {}


def _make_notify_cb(engine_ref):
    def _cb():
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

    _loop_engines = weakref.WeakKeyDictionary()
    _lock = threading.Lock()

    def __init__(self, loop, lib, ffi):
        self._loop_ref = weakref.ref(loop)
        self._lib = lib
        self._ffi = ffi
        self._closed = False
        self._read_fd = -1
        self._write_fd = -1
        self._queue = ffi.NULL
        r, w = os.pipe()
        try:
            os.set_blocking(r, False)
            os.set_blocking(w, False)
            self._read_fd = r
            self._write_fd = w
            self._queue = lib.pynng_mpsc_queue_new(w)
            self._slots = {}
            self._slot_counter = 0
            self._batch_size = 256
            self._batch_buf = ffi.new(f"uintptr_t[{self._batch_size}]")
            loop.add_reader(self._read_fd, _make_notify_cb(weakref.ref(self)))
        except BaseException:
            self.close()
            if self._queue != ffi.NULL:
                lib.pynng_mpsc_queue_free(self._queue)
                self._queue = ffi.NULL
            raise

    @property
    def _loop(self):
        return self._loop_ref()

    @classmethod
    def get_for_loop(cls, loop, lib, ffi):
        if loop is None or loop.is_closed() or not hasattr(loop, "add_reader"):
            return None
        with cls._lock:
            # Opportunistically close engines belonging to closed event loops
            for existing_loop, by_lib in list(cls._loop_engines.items()):
                if existing_loop.is_closed():
                    for eng in by_lib.values():
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

    def _on_notify(self):
        if self._closed or self._read_fd < 0:
            return
        try:
            os.read(self._read_fd, 65536)
        except (BlockingIOError, OSError):
            pass
        if self._queue == self._ffi.NULL:
            return
        while True:
            count = self._lib.pynng_mpsc_drain_batch(
                self._queue, self._batch_buf, self._batch_size
            )
            if count == 0:
                break
            for i in range(count):
                slot_id = self._batch_buf[i]
                fut = self._slots.pop(slot_id, None)
                if fut is not None and not fut.done():
                    fut.set_result(None)

    def register(self, fut):
        self._slot_counter = (self._slot_counter + 1) & 0x7FFFFFFF
        if self._slot_counter == 0:
            self._slot_counter = 1
        slot_id = self._slot_counter
        self._slots[slot_id] = fut
        return slot_id

    def unregister(self, slot_id):
        self._slots.pop(slot_id, None)

    def close(self):
        if self._closed:
            return
        self._closed = True
        if self._queue != self._ffi.NULL and hasattr(
            self._lib, "pynng_mpsc_queue_close"
        ):
            self._lib.pynng_mpsc_queue_close(self._queue)
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

    def __del__(self):
        try:
            self.close()
            if getattr(self, "_queue", None) not in (None, self._ffi.NULL):
                self._lib.pynng_mpsc_queue_free(self._queue)
                self._queue = self._ffi.NULL
        except Exception:
            pass


@ffi.def_extern()
def _async_complete(void_p):
    """
    This is the callback provided to nng_aio_* functions which completes the
    Python future argument passed to it.  It schedules _set_future_finished
    to run to complete the future associated with the event.
    """
    # this is not a public interface, so asserting invariants is good.
    assert isinstance(void_p, ffi.CData)
    id = int(ffi.cast("size_t", void_p))

    rescheduler = _aio_map.pop(id, None)
    if rescheduler is None:
        return
    rescheduler()


def asyncio_helper(aio):
    """
    Returns a callable that will be passed to _async_complete.  The callable is
    responsible for rescheduling the event loop

    """
    _lib = aio._lib
    _ffi = aio._ffi
    loop = asyncio.get_running_loop()
    fut = loop.create_future()

    async def wait_for_aio():
        already_called_nng_aio_cancel = False
        while True:
            try:
                await asyncio.shield(fut)
            except asyncio.CancelledError:
                if not already_called_nng_aio_cancel:
                    _lib.nng_aio_cancel(aio.aio)
                    already_called_nng_aio_cancel = True
            else:
                break
        err = _lib.nng_aio_result(aio.aio)
        if already_called_nng_aio_cancel or err == _lib.NNG_ECANCELED:
            raise asyncio.CancelledError
        check_err(err, lib=_lib, ffi=_ffi)

    def _set_future_finished(fut):
        if not fut.done():
            fut.set_result(None)

    def rescheduler():
        loop.call_soon_threadsafe(_set_future_finished, fut)

    return wait_for_aio(), rescheduler


def trio_helper(aio):
    # Record the info needed to get back into this task
    import trio

    _lib = aio._lib
    _ffi = aio._ffi

    token = trio.lowlevel.current_trio_token()
    task = trio.lowlevel.current_task()

    def resumer():
        token.run_sync_soon(trio.lowlevel.reschedule, task)

    async def wait_for_aio():
        # Machinery to handle Trio cancellation, and convert it into nng cancellation
        raise_cancel_fn = None

        def abort_fn(raise_cancel_arg):
            # This function is called if Trio wants to cancel the operation.
            # First, ask nng to cancel the operation.
            _lib.nng_aio_cancel(aio.aio)
            # nng cancellation doesn't happen immediately, so we need to save the raise_cancel function
            # into the enclosing scope to call it later, after we find out if the cancellation actually happened.
            nonlocal raise_cancel_fn
            raise_cancel_fn = raise_cancel_arg
            # And then tell Trio that we weren't able to cancel the operation immediately, so it should keep
            # waiting.
            return trio.lowlevel.Abort.FAILED

        # Put the Trio task to sleep.
        await trio.lowlevel.wait_task_rescheduled(abort_fn)

        err = _lib.nng_aio_result(aio.aio)
        if err == _lib.NNG_ECANCELED:
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
    _aio_helper_map = {
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

    def __init__(self, obj, async_backend, _lib=None, _ffi=None, *, _use_mpsc=True):
        # set to None now so we can know if we need to free it later
        # This should be at the top of __init__ so that __del__ doesn't raise
        # an unexpected AttributeError if something funky happens
        self.aio = None
        self._mpsc_engine = None
        self._aio_entry = None
        self._current_slot = None
        self._current_fut = None
        self._sending = False
        self.cb_arg = None
        self.awaitable = None

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

        self._lib = _lib
        self._ffi = _ffi

        # this is not a public interface, let's make some assertions
        assert isinstance(obj, (_base.Socket, _base.Context))
        # we need to choose the correct nng lib functions based on the type of
        # object we've been passed; but really, all the logic is identical
        if isinstance(obj, _base.Socket):
            self._nng_obj = obj.socket
            # Use _aio_recv_fn / _aio_send_fn properties if available,
            # otherwise fall back to v1 function names
            if getattr(obj, "_aio_recv_fn", None) is not None:
                self._lib_arecv = obj._aio_recv_fn
                self._lib_asend = obj._aio_send_fn
            else:
                self._lib_arecv = _lib.nng_recv_aio
                self._lib_asend = _lib.nng_send_aio
        else:
            self._nng_obj = obj.context
            self._lib_arecv = _lib.nng_ctx_recv
            self._lib_asend = _lib.nng_ctx_send
        self.obj = obj
        if async_backend is None:
            async_backend = sniffio.current_async_library()
        if async_backend not in self._aio_helper_map:
            raise ValueError(
                "The async backend {} is not currently supported.".format(async_backend)
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
            self._aio_entry = _lib.pynng_aio_entry_new(
                _ffi.NULL, 0, self._mpsc_engine._queue
            )
            aio_p = _ffi.new("nng_aio **")
            check_err(
                _lib.nng_aio_alloc(
                    aio_p, _lib.pynng_native_aio_complete, self._aio_entry
                ),
                lib=_lib,
                ffi=_ffi,
            )
            self.aio = aio_p[0]
        else:
            self.awaitable, self.cb_arg = self._aio_helper_map[async_backend](self)
            aio_p = _ffi.new("nng_aio **")
            _aio_map[id(self.cb_arg)] = self.cb_arg
            idarg = id(self.cb_arg)
            as_void = _ffi.cast("void *", idarg)
            try:
                check_err(
                    _lib.nng_aio_alloc(aio_p, _lib._async_complete, as_void),
                    lib=_lib,
                    ffi=_ffi,
                )
            except BaseException:
                _aio_map.pop(idarg, None)
                raise
            self.aio = aio_p[0]

    def is_valid_for_current_loop(self):
        engine = self._mpsc_engine
        if engine is None or engine._closed or self.aio is None or self._aio_entry is None:
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
            and bool(self._lib.pynng_aio_entry_is_idle(self._aio_entry))
        )

    def _prepare_aio(self):
        if self._mpsc_engine is not None:
            loop = self._mpsc_engine._loop
            if loop is None or loop.is_closed():
                raise RuntimeError("Event loop is closed")
            fut = loop.create_future()
            slot = self._mpsc_engine.register(fut)
            self._current_slot = slot
            self._current_fut = fut
            self._lib.pynng_aio_entry_set_slot_id(self._aio_entry, slot)

    def _cleanup_prepared_aio(self):
        if self._mpsc_engine is not None:
            if self._current_slot is not None:
                self._mpsc_engine.unregister(self._current_slot)
                self._current_slot = None
            self._current_fut = None
            if self._aio_entry is not None:
                self._lib.pynng_aio_entry_set_slot_id(self._aio_entry, 0)

    async def _wait_for_aio(self):
        if self._mpsc_engine is not None:
            fut = self._current_fut
            _lib = self._lib
            already_cancelled = False
            try:
                while True:
                    try:
                        await asyncio.shield(fut)
                    except asyncio.CancelledError:
                        if not already_cancelled:
                            _lib.nng_aio_cancel(self.aio)
                            already_cancelled = True
                    else:
                        break
            finally:
                if self._current_slot is not None:
                    self._mpsc_engine.unregister(self._current_slot)
                    self._current_slot = None
                self._current_fut = None
                if self._aio_entry is not None:
                    _lib.pynng_aio_entry_set_slot_id(self._aio_entry, 0)
            err = _lib.nng_aio_result(self.aio)
            if already_cancelled or err == _lib.NNG_ECANCELED:
                raise asyncio.CancelledError
            check_err(err, lib=_lib, ffi=self._ffi)
        else:
            await self.awaitable

    async def arecv(self):
        msg = await self.arecv_msg()
        return msg.bytes

    async def arecv_msg(self):
        _lib = self._lib
        _ffi = self._ffi
        self._prepare_aio()
        try:
            check_err(self._lib_arecv(self._nng_obj, self.aio), lib=_lib, ffi=_ffi)
        except BaseException:
            self._cleanup_prepared_aio()
            raise
        try:
            await self._wait_for_aio()
        except BaseException:
            msg = _lib.nng_aio_get_msg(self.aio)
            if msg != _ffi.NULL:
                _lib.nng_aio_set_msg(self.aio, _ffi.NULL)
                _lib.nng_msg_free(msg)
            raise
        check_err(_lib.nng_aio_result(self.aio), lib=_lib, ffi=_ffi)
        msg = _lib.nng_aio_get_msg(self.aio)
        _lib.nng_aio_set_msg(self.aio, _ffi.NULL)
        from ._base import Message, Socket, Context

        # Use the socket's message class if available
        msg_cls = Message
        if isinstance(self.obj, Socket) and self.obj._message_class is not None:
            msg_cls = self.obj._message_class
        elif (
            isinstance(self.obj, Context)
            and self.obj._socket._message_class is not None
        ):
            msg_cls = self.obj._socket._message_class
        return msg_cls(msg, _lib=_lib, _ffi=_ffi)

    async def asend(self, data):
        _lib = self._lib
        _ffi = self._ffi
        msg_p = _ffi.new("nng_msg **")
        check_err(_lib.nng_msg_alloc(msg_p, 0), lib=_lib, ffi=_ffi)
        msg = msg_p[0]
        try:
            if isinstance(data, bytes):
                buf = data
            else:
                buf = _ffi.from_buffer(data)
            check_err(_lib.nng_msg_append(msg, buf, len(data)), lib=_lib, ffi=_ffi)
            self._prepare_aio()
            _lib.nng_aio_set_msg(self.aio, msg)
            self._sending = True
            check_err(self._lib_asend(self._nng_obj, self.aio), lib=_lib, ffi=_ffi)
        except BaseException:
            self._sending = False
            self._cleanup_prepared_aio()
            _lib.nng_aio_set_msg(self.aio, _ffi.NULL)
            _lib.nng_msg_free(msg)
            raise
        try:
            await self._wait_for_aio()
        except BaseException:
            leftover = _lib.nng_aio_get_msg(self.aio)
            if leftover != _ffi.NULL:
                _lib.nng_aio_set_msg(self.aio, _ffi.NULL)
                _lib.nng_msg_free(leftover)
            raise
        finally:
            self._sending = False

    async def asend_msg(self, msg):
        """
        Asynchronously send a Message

        """
        _lib = self._lib
        _ffi = self._ffi
        msg._ensure_can_send()
        self._prepare_aio()
        _lib.nng_aio_set_msg(self.aio, msg._nng_msg)
        msg._mem_freed = True
        self._sending = True
        try:
            check_err(self._lib_asend(self._nng_obj, self.aio), lib=_lib, ffi=_ffi)
        except BaseException:
            self._sending = False
            self._cleanup_prepared_aio()
            _lib.nng_aio_set_msg(self.aio, _ffi.NULL)
            _lib.nng_msg_free(msg._nng_msg)
            raise
        try:
            await self._wait_for_aio()
        except BaseException:
            leftover = _lib.nng_aio_get_msg(self.aio)
            if leftover != _ffi.NULL:
                _lib.nng_aio_set_msg(self.aio, _ffi.NULL)
                _lib.nng_msg_free(leftover)
            raise
        finally:
            self._sending = False

    def _free(self):
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
            # Cancel in-flight AIO before freeing to prevent deadlock during GC.
            _lib.nng_aio_cancel(self.aio)
            _lib.nng_aio_wait(self.aio)
            if self._sending:
                leftover = _lib.nng_aio_get_msg(self.aio)
                if leftover != _ffi.NULL:
                    _lib.nng_aio_set_msg(self.aio, _ffi.NULL)
                    _lib.nng_msg_free(leftover)
                self._sending = False
            _lib.nng_aio_free(self.aio)
            self.aio = None

        if self._aio_entry is not None:
            self._lib.pynng_aio_entry_free(self._aio_entry)
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

    def __enter__(self):
        return self

    def __exit__(self, *_exc_info):
        self._free()

    def __del__(self):
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
    )

    def __init__(self, s1, s2=None, async_backend=None, *, _use_mpsc=True):
        self.aio = None
        self._mpsc_engine = None
        self._aio_entry = None
        self._current_slot = None
        self.cb_arg = None
        self.awaitable = None
        self.s1 = s1
        self.s2 = s2
        self._lib = getattr(s1, "_lib", lib)
        self._ffi = getattr(s1, "_ffi", ffi)
        sock1 = s1.socket if hasattr(s1, "socket") else s1
        if s2 is None:
            sock2 = self._ffi.new("nng_socket *")[0]
        else:
            sock2 = s2.socket if hasattr(s2, "socket") else s2
        self._sock1 = sock1
        self._sock2 = sock2

        if async_backend is None:
            if hasattr(s1, "_async_backend") and s1._async_backend is not None:
                async_backend = s1._async_backend
            else:
                async_backend = sniffio.current_async_library()
        if async_backend not in AIOHelper._aio_helper_map:
            raise ValueError(
                "The async backend {} is not currently supported.".format(async_backend)
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
            self._aio_entry = self._lib.pynng_aio_entry_new(
                self._ffi.NULL, 0, self._mpsc_engine._queue
            )
            aio_p = self._ffi.new("nng_aio **")
            check_err(
                self._lib.nng_aio_alloc(
                    aio_p, self._lib.pynng_native_aio_complete, self._aio_entry
                ),
                lib=self._lib,
                ffi=self._ffi,
            )
            self.aio = aio_p[0]
        else:
            self.awaitable, self.cb_arg = AIOHelper._aio_helper_map[async_backend](self)
            aio_p = self._ffi.new("nng_aio **")
            _aio_map[id(self.cb_arg)] = self.cb_arg
            idarg = id(self.cb_arg)
            as_void = self._ffi.cast("void *", idarg)
            try:
                check_err(
                    self._lib.nng_aio_alloc(aio_p, self._lib._async_complete, as_void),
                    lib=self._lib,
                    ffi=self._ffi,
                )
            except BaseException:
                _aio_map.pop(idarg, None)
                raise
            self.aio = aio_p[0]

    async def run(self):
        try:
            if self._mpsc_engine is not None:
                loop = self._mpsc_engine._loop
                if loop is None or loop.is_closed():
                    raise RuntimeError("Event loop is closed")
                fut = loop.create_future()
                slot = self._mpsc_engine.register(fut)
                self._current_slot = slot
                self._lib.pynng_aio_entry_set_slot_id(self._aio_entry, slot)
                self._lib.nng_device_aio(self.aio, self._sock1, self._sock2)
                _lib = self._lib
                already_cancelled = False
                try:
                    while True:
                        try:
                            await asyncio.shield(fut)
                        except asyncio.CancelledError:
                            if not already_cancelled:
                                _lib.nng_aio_cancel(self.aio)
                                already_cancelled = True
                        else:
                            break
                finally:
                    if self._current_slot is not None:
                        self._mpsc_engine.unregister(self._current_slot)
                        self._current_slot = None
                    if self._aio_entry is not None:
                        _lib.pynng_aio_entry_set_slot_id(self._aio_entry, 0)
                err = _lib.nng_aio_result(self.aio)
                if already_cancelled or err == _lib.NNG_ECANCELED:
                    raise asyncio.CancelledError
                check_err(err, lib=_lib, ffi=self._ffi)
            else:
                self._lib.nng_device_aio(self.aio, self._sock1, self._sock2)
                await self.awaitable
        finally:
            self._free()

    def _free(self):
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
            self._lib.nng_aio_cancel(self.aio)
            self._lib.nng_aio_wait(self.aio)
            self._lib.nng_aio_free(self.aio)
            self.aio = None

        if self._aio_entry is not None:
            self._lib.pynng_aio_entry_free(self._aio_entry)
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

    def __enter__(self):
        return self

    def __exit__(self, *_exc_info):
        self._free()

    def __del__(self):
        self._free()
