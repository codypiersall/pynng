"""A collection that runs a finalizer in the middle of a registry update.

A cyclic collection can run on any thread at any bytecode boundary, also while
that thread is inside pynng code. If the finalizer of an unreachable object
then takes a lock that the interrupted code holds, the thread deadlocks on
itself. Each script forces the collection at the registry update, so a
deadlock is a timeout instead of an intermittent hang.
"""

import subprocess
import sys

import pytest

_SOCKET_REGISTRY = """
import gc
import importlib
import sys
import weakref

from pynng import _base

pynng = importlib.import_module(sys.argv[1])


# A finalizer that this collection runs can reach the registry again. PyPy
# refuses a nested gc.collect() there, so collect only at the outer level.
_collecting = False


def collect():
    global _collecting
    if _collecting:
        return
    _collecting = True
    try:
        gc.collect()
    finally:
        _collecting = False


class Registry(dict):
    def __setitem__(self, key, value):
        collect()
        super().__setitem__(key, value)

    def get(self, key, default=None):
        collect()
        return super().get(key, default)


def unclosed_garbage_socket():
    s = pynng.Pair0()
    s.cycle = s
    return weakref.ref(s)


gc.disable()
_base._active_handles = Registry(_base._active_handles)
garbage = unclosed_garbage_socket()
s = pynng.Pair0()
assert garbage() is None
garbage = unclosed_garbage_socket()
s.close()
assert garbage() is None
print("NO_DEADLOCK")
"""

_AIO_MAP = """
import asyncio
import gc

import pynng
from pynng import _aio


# A finalizer that this collection runs can reach the registry again. PyPy
# refuses a nested gc.collect() there, so collect only at the outer level.
_collecting = False


def collect():
    global _collecting
    if _collecting:
        return
    _collecting = True
    try:
        gc.collect()
    finally:
        _collecting = False


class AioMap(dict):
    def __setitem__(self, key, value):
        collect()
        super().__setitem__(key, value)

    def pop(self, key, default=None):
        collect()
        return super().pop(key, default)


def unfreed_garbage_aio(sock):
    box = [_aio.AIOHelper(sock, "asyncio", _use_mpsc=False)]
    box.append(box)
    return id(box[0].cb_arg)


async def main():
    with pynng.Pair0() as sock:
        garbage = unfreed_garbage_aio(sock)
        aio = _aio.AIOHelper(sock, "asyncio", _use_mpsc=False)
        assert garbage not in _aio._aio_map
        garbage = unfreed_garbage_aio(sock)
        aio._free()
        assert garbage not in _aio._aio_map


gc.disable()
_aio._aio_map = AioMap(_aio._aio_map)
asyncio.run(main())
print("NO_DEADLOCK")
"""


_DEVICE = """
import asyncio
import gc
import importlib
import sys
import threading
import time
import weakref

from pynng import _aio

pynng = importlib.import_module(sys.argv[1])


# A finalizer that this collection runs can reach the device lock again. PyPy
# refuses a nested gc.collect() there, so collect only at the outer level.
_collecting = False


def collect():
    global _collecting
    if _collecting:
        return
    _collecting = True
    try:
        gc.collect()
    finally:
        _collecting = False


class DeviceAios(set):
    def add(self, aio):
        collect()
        super().add(aio)

    def discard(self, aio):
        collect()
        super().discard(aio)


# For each finalizer of the garbage below: was its thread in a device section?
in_section = []


class GarbageSocket(pynng.Pair0):
    def __del__(self):
        in_section.append(_aio._in_device_section())
        super().__del__()


class GarbageDeviceAIO(_aio.DeviceAIO):
    __slots__ = ("__weakref__",)

    def __del__(self):
        in_section.append(_aio._in_device_section())
        super().__del__()


garbage = []


def make_garbage(sock1, sock2):
    s = GarbageSocket()
    s.cycle = s
    garbage.append(weakref.ref(s))
    box = [GarbageDeviceAIO(sock1, sock2, "asyncio")]
    box.append(box)
    garbage.append(weakref.ref(box[0]))


def run_device(rep, req):
    try:
        pynng.device(rep, req)
    except pynng.Closed:
        pass


async def main():
    rep = pynng.Rep0(raw=True)
    req = pynng.Req0(raw=True)
    rep._device_aios = DeviceAios()
    idle1 = pynng.Rep0(raw=True)
    idle2 = pynng.Req0(raw=True)
    make_garbage(idle1, idle2)
    device = threading.Thread(target=run_device, args=(rep, req))
    device.start()
    deadline = time.monotonic() + 30
    while not rep._device_aios:
        assert time.monotonic() < deadline, "device did not start"
        time.sleep(0.01)
    make_garbage(idle1, idle2)
    rep.close()
    device.join()
    for t in threading.enumerate():
        if t.name in ("pynng-close", "pynng-device-free"):
            t.join()
    # Each finalizer ran in a device section, and the work it handed to
    # another thread finished: nothing holds the garbage any more.
    assert in_section == [True] * 4, in_section
    gc.collect()
    assert [r() for r in garbage] == [None] * 4
    req.close()
    idle1.close()
    idle2.close()


gc.disable()
asyncio.run(main())
print("NO_DEADLOCK")
"""

_DEVICE_AT_EXIT = """
import asyncio
import importlib
import sys

from pynng._aio import DeviceAIO

pynng = importlib.import_module(sys.argv[1])
lib = importlib.import_module(sys.argv[2])

a = pynng.Pair0(listen="inproc://device-at-exit-a")
b = pynng.Pair0(listen="inproc://device-at-exit-b")


async def main():
    global dev
    dev = DeviceAIO(a, b, "asyncio", _default_lib=lib.lib, _default_ffi=lib.ffi)
    # Without the MPSC engine (the Windows Proactor loop has no add_reader),
    # the constructor makes the run() coroutine, and this script never runs it.
    if dev.awaitable is not None:
        dev.awaitable.close()


asyncio.run(main())
"""


def _run(tmp_path, code, *args):
    # Run outside the source tree, so the child imports the installed pynng
    # (or PYTHONPATH) and not the uncompiled checkout through sys.path[0].
    try:
        proc = subprocess.run(
            [sys.executable, "-c", code, *args],
            cwd=tmp_path,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
    except subprocess.TimeoutExpired:
        pytest.fail("deadlock: a finalizer blocked on a lock its thread held")
    assert proc.returncode == 0, proc.stderr
    assert "NO_DEADLOCK" in proc.stdout


@pytest.mark.parametrize("module", ["pynng", "pynng.v2"])
def test_socket_finalizer_during_registry_update(tmp_path, module):
    _run(tmp_path, _SOCKET_REGISTRY, module)


def test_aio_finalizer_during_aio_map_update(tmp_path):
    _run(tmp_path, _AIO_MAP)


@pytest.mark.parametrize("module", ["pynng", "pynng.v2"])
def test_finalizers_during_device_start_and_stop(tmp_path, module):
    _run(tmp_path, _DEVICE, module)


@pytest.mark.parametrize(
    "module, nng", [("pynng", "pynng._nng"), ("pynng.v2", "pynng._nng_v2")]
)
def test_device_aio_freed_at_interpreter_exit(tmp_path, module, nng):
    proc = subprocess.run(
        [sys.executable, "-c", _DEVICE_AT_EXIT, module, nng],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    assert proc.stderr == ""
