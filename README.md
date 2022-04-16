This is pynng.
==============

[![MIT License](https://img.shields.io/badge/license-MIT-blue.svg)](https://github.com/codypiersall/pynng/blob/master/LICENSE.txt)
[![PyPI Version](https://img.shields.io/pypi/v/pynng.svg)](https://pypi.org/project/pynng)
[![Build succeeding](https://github.com/codypiersall/pynng/workflows/smoketest/badge.svg)](https://github.com/codypiersall/pynng/actions)
[![Wheels building](https://github.com/codypiersall/pynng/workflows/build-wheels/badge.svg)](https://github.com/codypiersall/pynng/actions)
[![docs](https://img.shields.io/readthedocs/pynng.svg)](https://pynng.readthedocs.io)

Ergonomic bindings for [nanomsg next generation] \(nng), in Python.
pynng provides a nice interface on top of the full power of nng.  nng, and
therefore pynng, make it easy to communicate between processes on a single
computer or computers across a network.  This library is compatible with Python
≥ 3.5.  nng is the [rewriting](https://nanomsg.github.io/nng/RATIONALE.html) of
[Nanomsg](https://nanomsg.org/), which is the spiritual successor to [ZeroMQ](http://zeromq.org/).

Goals
-----

Provide a Pythonic, works-out-of-the box library on Windows and Unix-y
platforms.  Like nng itself, the license is MIT, so it can be used without
restriction.

Installation
------------

On Windows, MacOS, and Linux, the usual

    pip3 install pynng

should suffice.  Note that on 32-bit Linux and on macOS no binary distributions
are available, so [CMake](https://cmake.org/) is also required.

Building from the GitHub repo works as well, natch:

    git clone https://github.com/codypiersall/pynng
    cd pynng
    pip3 install -e .

(If you want to run tests, you also need to `pip3 install trio curio pytest pytest-asyncio pytest-trio pytest-curio`,
then just run `pytest test`.)

pynng might work on the BSDs as well.  Who knows!

Using pynng
-----------

Using pynng is easy peasy:

```python
from pynng import Pair0

s1 = Pair0()
s1.listen('tcp://127.0.0.1:54321')
s2 = Pair0()
s2.dial('tcp://127.0.0.1:54321')
s1.send(b'Well hello there')
print(s2.recv())
s1.close()
s2.close()
```

Since pynng sockets support setting most parameters in the socket's `__init__`
method and is a context manager, the above code can be written much shorter:

```python
from pynng import Pair0

with Pair0(listen='tcp://127.0.0.1:54321') as s1, \
        Pair0(dial='tcp://127.0.0.1:54321') as s2:
    s1.send(b'Well hello there')
    print(s2.recv())
```

### Using pynng with an async framework

Asynchronous sending also works with

[curio](https://github.com/dabeaz/curio), [trio](https://trio.readthedocs.io/en/latest/) and
[asyncio](https://docs.python.org/3/library/asyncio.html).  Here is an example
using trio:


```python
import pynng
import trio

async def send_and_recv(sender, receiver, message):
    await sender.asend(message)
    return await receiver.arecv()

with pynng.Pair0(listen='tcp://127.0.0.1:54321') as s1, \
        pynng.Pair0(dial='tcp://127.0.0.1:54321') as s2:
    received = trio.run(send_and_recv, s1, s2, b'hello there old pal!')
    assert received == b'hello there old pal!'
```

Many other protocols are available as well:

* `Pair0`: one-to-one, bidirectional communication.
* `Pair1`: one-to-one, bidirectional communication, but also supporting
  polyamorous sockets
* `Pub0`, `Sub0`: publish/subscribe sockets.
* `Surveyor0`, `Respondent0`: Broadcast a survey to respondents, e.g. to find
  out what services are available.
* `Req0`, `Rep0`: request/response pattern.
* `Push0`, `Pull0`: Aggregate messages from multiple sources and load balance
  among many destinations.

Examples
--------

Some examples (okay, just two examples) are available in the
[examples](https://github.com/codypiersall/pynng/tree/master/examples)
directory.

Git Branch Policy
-----------------

The **only** stable branch is `master`.  There will *never* be a `git push -f`
on master.  On the other hand, all other branches are not considered stable;
they may be deleted, rebased, force-pushed, and any other manner of funky
business.

[nanomsg next generation]: https://nanomsg.github.io/nng/index.html
