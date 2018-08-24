This is pynng.
==============

Ergonomic bindings for [nanomsg next generation] \(nng), in Python.
pynng provides a nice interface on top of the full power of nng.  nng makes it
easy to communicate between processes on a single computer or computers across
a network.  Like, really easy.  So easy, even an old chunk of coal like me can
do it.

Goals
=====

Provide a Pythonic, works-out-of-the box on Windows and Unix-y platforms.  Like
nng itself, the license is MIT, so it can be used without restriction.

This project is in early stages now; support for Mac is non-existent, support
for Windows is limited.  None of the installation is automated.

TODO
====

* Get CI going for Linux and Windows, including building manylinux wheels if
  possible.
* Docs.
* Support Mac

[nanomsg next generation]: https://nanomsg.github.io/nng/index.html
