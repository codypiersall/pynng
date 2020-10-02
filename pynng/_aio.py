"""
Helpers for AIO functions
"""

import asyncio
import sniffio

from ._nng import ffi, lib
import pynng
from .exceptions import check_err


@ffi.def_extern()
def _send_complete(void_p):
    """
    This is called when an async send is complete
    """

    aio = ffi.from_handle(void_p)
    if aio.send_callback:
      aio.send_callback()

@ffi.def_extern()
def _recv_complete(void_p):
    """
    This is called when an async receive is complete
    """

    aio = ffi.from_handle(void_p)
    if aio.recv_callback:
      aio.recv_callback()

def asyncio_helper(aio_p):
    """
    Returns a callable that will be passed to _async_complete.  The callable is
    responsible for rescheduling the event loop

    """

    loop = asyncio.get_running_loop()
    fut = loop.create_future()

    def _set_future_finished(fut):
      if not fut.cancelled():
        fut.set_result(None)

    def callback():
      loop.call_soon_threadsafe(_set_future_finished, fut)

    async def wait_for_aio():
        while True:
            try:
                await asyncio.shield(fut)
            except asyncio.CancelledError:
                if not fut.done():
                  lib.nng_aio_cancel(aio_p)
                else:
                  raise asyncio.CancelledError
            else:
                break

        err = lib.nng_aio_result(aio_p)
        if err == lib.NNG_ECANCELED:
            raise asyncio.CancelledError
        check_err(err)

    return wait_for_aio(), callback

def trio_helper(aio_p):
    # Record the info needed to get back into this task
    import trio
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
            lib.nng_aio_cancel(aio_p)
            # nng cancellation doesn't happen immediately, so we need to save the raise_cancel function
            # into the enclosing scope to call it later, after we find out if the cancellation actually happened.
            nonlocal raise_cancel_fn
            raise_cancel_fn = raise_cancel_arg
            # And then tell Trio that we weren't able to cancel the operation immediately, so it should keep
            # waiting.
            return trio.lowlevel.Abort.FAILED

        # Put the Trio task to sleep.
        await trio.lowlevel.wait_task_rescheduled(abort_fn)

        err = lib.nng_aio_result(aio_p)
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
        'trio': trio_helper
    }

    def __init__(self, obj, async_backend):
        # set to None now so we can know if we need to free it later
        # This should be at the top of __init__ so that __del__ doesn't raise
        # an unexpected AttributeError if something funky happens
        self.send_aio = None
        self.recv_aio = None
        # this is not a public interface, let's make some assertions
        assert isinstance(obj, (pynng.Socket, pynng.Context))
        # we need to choose the correct nng lib functions based on the type of
        # object we've been passed; but really, all the logic is identical
        if isinstance(obj, pynng.Socket):
            self._nng_obj = obj.socket
            self._lib_arecv = lib.nng_recv_aio
            self._lib_asend = lib.nng_send_aio
        else:
            self._nng_obj = obj.context
            self._lib_arecv = lib.nng_ctx_recv
            self._lib_asend = lib.nng_ctx_send
        self.obj = obj

        if async_backend is None:
            try:
                async_backend = sniffio.current_async_library()
            except sniffio.AsyncLibraryNotFoundError:
                return

        if async_backend not in self._aio_helper_map:
            raise ValueError(
                'The async backend {} is not currently supported.'
                .format(async_backend)
            )

        self.handle = ffi.new_handle(self)

        send_aio_p = ffi.new('nng_aio **')
        lib.nng_aio_alloc(send_aio_p, lib._send_complete, self.handle)
        self.send_aio = send_aio_p[0]

        recv_aio_p = ffi.new('nng_aio **')
        lib.nng_aio_alloc(recv_aio_p, lib._recv_complete, self.handle)
        self.recv_aio = recv_aio_p[0]

        self.helper = self._aio_helper_map[async_backend]

        self.send_callback = None
        self.recv_callback = None

    async def arecv(self):
        msg = await self.arecv_msg()
        return msg.bytes

    async def arecv_msg(self):
        (awaitable, self.recv_callback) = self.helper(self.recv_aio)
        check_err(self._lib_arecv(self._nng_obj, self.recv_aio))
        await awaitable
        check_err(lib.nng_aio_result(self.recv_aio))
        msg = lib.nng_aio_get_msg(self.recv_aio)
        return pynng.Message(msg)

    async def asend(self, data):
        (awaitable, self.send_callback) = self.helper(self.send_aio)

        msg_p = ffi.new('nng_msg **')
        check_err(lib.nng_msg_alloc(msg_p, 0))
        msg = msg_p[0]
        check_err(lib.nng_msg_append(msg, data, len(data)))
        check_err(lib.nng_aio_set_msg(self.send_aio, msg))
        check_err(self._lib_asend(self._nng_obj, self.send_aio))
        return await awaitable

    async def asend_msg(self, msg):
        """
        Asynchronously send a Message

        """
        (awaitable, self.send_callback) = self.helper(self.send_aio)
        lib.nng_aio_set_msg(self.send_aio, msg._nng_msg)
        check_err(self._lib_asend(self._nng_obj, self.send_aio))
        msg._mem_freed = True
        return await awaitable

    def _free(self):
        """
        Free resources allocated with nng
        """
        # TODO: Do we need to check if self.awaitable is not finished?
        if self.send_aio is not None:
            lib.nng_aio_free(self.send_aio)
            self.send_aio = None

        if self.recv_aio is not None:
            lib.nng_aio_free(self.recv_aio)
            self.recv_aio = None

    def __enter__(self):
        return self

    def __exit__(self, *_exc_info):
        self._free()

    def __del__(self):
        self._free()
