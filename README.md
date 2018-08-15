Python bindings for Nanomsg, using cffi

Goals
=====

Provide a Pythonic, works-out-of-the box on Windows and Unix-y platforms.  Like
nng itself, the license is MIT, so it can be used without restriction.

This project is in the very early stages now; support for Mac is non-existent,
support for Windows is limited.

TODO
====

* Right now I'm modifying the CMake build file to set
  `CMAKE_POSITION_INDEPENDENT_CODE`.  This avoids problems when linking into
  the final .so file, but there is probably a better way to do it.
  Additionally, I only do this on Linux; on Windows I leave CMake alone.
* Generating the API file is fragile, becuase it is not remotely C syntax
  aware; it's just dumb old sed.
* Do the right thing for 32/64 bit Python on Windows.
* Support Mac
