"""
Helpers for AIO functions
"""

import asyncio
import sniffio

from ._nng import ffi, lib
from .exceptions import check_err


# global variable for mapping asynchronous operations with the Python data
# assocated with them.  Key is id(obj), value is obj
_aio_map = {}


@ffi.def_extern()
def _async_complete(void_p):
    """
    This is the callback provided to nng_aio_* functions which completes the
    Python future argument passed to it.  It schedules _set_future_finished
    to run to complete the future associated with the event.
    """
    # this is not a public interface, so asserting invariants is good.
    assert isinstance(void_p, ffi.CData)
    id = int(ffi.cast('size_t', void_p))

    rescheduler = _aio_map.pop(id)
    rescheduler()


def asyncio_helper(aio):
    """
    Returns a callable that will be passed to _async_complete.  The callable is
    responsible for rescheduling the event loop

    """
    loop = asyncio.get_event_loop()
    fut = loop.create_future()

    async def wait_for_aio():
        already_called_nng_aio_cancel = False
        while True:
            try:
                await asyncio.shield(fut)
            except asyncio.CancelledError:
                if not already_called_nng_aio_cancel:
                    lib.nng_aio_cancel(aio.aio)
                    already_called_nng_aio_cancel = True
            else:
                break
        err = lib.nng_aio_result(aio.aio)
        if err == lib.NNG_ECANCELED:
            raise asyncio.CancelledError
        check_err(err)

    def _set_future_finished(fut):
        if not fut.done():
            fut.set_result(None)

    def rescheduler():
        loop.call_soon_threadsafe(_set_future_finished, fut)

    return fut, rescheduler


def trio_helper(aio):
    # Record the info needed to get back into this task
    import trio
    token = trio.hazmat.current_trio_token()
    task = trio.hazmat.current_task()

    def resumer():
        token.run_sync_soon(trio.hazmat.reschedule, task)

    async def wait_for_aio():
        # Machinery to handle Trio cancellation, and convert it into nng cancellation
        raise_cancel_fn = None

        def abort_fn(raise_cancel_arg):
            # This function is called if Trio wants to cancel the operation.
            # First, ask nng to cancel the operation.
            lib.nng_aio_cancel(aio.aio)
            # nng cancellation doesn't happen immediately, so we need to save the raise_cancel function
            # into the enclosing scope to call it later, after we find out if the cancellation actually happened.
            nonlocal raise_cancel_fn
            raise_cancel_fn = raise_cancel_arg
            # And then tell Trio that we weren't able to cancel the operation immediately, so it should keep
            # waiting.
            return trio.hazmat.Abort.FAILED

        # Put the Trio task to sleep.
        await trio.hazmat.wait_task_rescheduled(abort_fn)

        err = lib.nng_aio_result(aio.aio)
        if err == lib.NNG_ECANCELED:
            # This operation was successfully cancelled.
            # Call the function Trio gave us, which raises the proper Trio cancellation exception
            raise_cancel_fn()
        check_err(err)

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
    #
    # It might just be clearer to look at the implementation of trio_helper and
    # asyncio_helper to get an idea of what the functions need to do.
    _aio_helper_map = {
        'asyncio': asyncio_helper,
        'trio': trio_helper,
    }

    def __init__(self, socket, async_backend):
        self.socket = socket
        # set to None now so we can know if we need to free it later
        self.aio = None
        self.msg = None
        if async_backend is None:
            async_backend = sniffio.current_async_library()
        if async_backend not in self._aio_helper_map:
            raise ValueError('The async backend {} is not currently supported.'.format(async_backend))
        self.awaitable, self.cb_arg = self._aio_helper_map[async_backend](self)
        aio_p = ffi.new('nng_aio **')
        _aio_map[id(self.cb_arg)] = self.cb_arg
        idarg = id(self.cb_arg)
        as_void = ffi.cast('void *', idarg)
        lib.nng_aio_alloc(aio_p, lib._async_complete, as_void)
        self.aio = aio_p[0]

    async def arecv(self):
        lib.nng_recv_aio(self.socket.socket, self.aio)
        await self.awaitable
        err = lib.nng_aio_result(self.aio)
        check_err(err)
        self.msg = lib.nng_aio_get_msg(self.aio)
        size = lib.nng_msg_len(self.msg)
        data = ffi.cast('char *', lib.nng_msg_body(self.msg))
        py_obj = bytes(ffi.buffer(data[0:size]))
        return py_obj

    async def asend(self, data):
        msg_p = ffi.new('nng_msg **')
        check_err(lib.nng_msg_alloc(msg_p, 0))
        msg = msg_p[0]
        lib.nng_msg_append(msg, data, len(data))
        lib.nng_aio_set_msg(self.aio, msg)
        lib.nng_send_aio(self.socket.socket, self.aio)
        return await self.awaitable

    def _free(self):
        """
        Free resources allocated with nng
        """
        if self.aio is not None:
            lib.nng_aio_free(self.aio)
            self.aio = None
        if self.msg is not None:
            lib.nng_msg_free(self.msg)
            self.msg = None

    def __enter__(self):
        return self

    def __exit__(self, *_exc_info):
        self._free()

    def __del__(self):
        self._free()


