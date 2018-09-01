This is pynng.
==============

Ergonomic bindings for [nanomsg next generation] \(nng), in Python.
pynng provides a nice interface on top of the full power of nng.  nng, and
therefore pynng, make it easy to communicate between processes on a single
computer or computers across a network.

Goals
=====

Provide a Pythonic, works-out-of-the box library on Windows and Unix-y
platforms.  Like nng itself, the license is MIT, so it can be used without
restriction.

Installation
============

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

Installing on Mac
-----------------

This project does not yet know how to build for Mac, because I don't have a Mac
to test on.  The tricky bit is letting cffi know the correct object file to
link to, and ensuring whatever the Mac equivalent of -fPIC is set when
compiling.

TODO
====

* Support Mac
* More docs

[nanomsg next generation]: https://nanomsg.github.io/nng/index.html
