This is pynng.
==============

Ergonomic bindings for [nanomsg next generation] \(nng), in Python.
pynng provides a nice interface on top of the full power of nng.  nng, and
therefore pynng, make it easy to communicate between processes on a single
computer or computers across a network.

Goals
-----

Provide a Pythonic, works-out-of-the box library on Windows and Unix-y
platforms.  Like nng itself, the license is MIT, so it can be used without
restriction.

Installation
------------

On Windows and 64-bit Linux, the usual

    pip install pynng

should suffice.  Building from source is a little convoluted, due to some
issues with the way the setup.py script is written.  Nevertheless, it can be
done:

    git clone https://github.com/codypiersall/pynng
    cd pynng
    pip install .
    python setup.py build
    python setup.py build_ext --inplace
    pytest

### Installing on Mac


This project does not yet know how to build for Mac, because I don't have a Mac
to test on.  The tricky bit is letting cffi know the correct object file to
link to, and ensuring whatever the Mac equivalent of -fPIC is set when
compiling.

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

Asynchronous sending also works with
[trio](https://trio.readthedocs.io/en/latest/) and
[asyncio](https://docs.python.org/3/library/asyncio.html).  Here is an example
using trio:


```python

import pynng
import trio


async def send_and_recv(sender, receiver, message):
    await sender.asend(message)
    return await receiver.arecv()

with Pair0(listen='tcp://127.0.0.1:54321') as s1, \
        Pair0(dial='tcp://127.0.0.1:54321') as s2:

    received = trio.run(s1, s2, b'hello there old pal!')
    assert recieved == 'hello there old pal!'

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

TODO
----

* Support Mac
* More docs

[nanomsg next generation]: https://nanomsg.github.io/nng/index.html
