Python bindings for Nanomsg, using cffi

TODO
====

* Right now I'm modifying the CMake build file to set
  `CMAKE_POSITION_INDEPENDENT_CODE`.  This avoids problems when linking into
  the final .so file, but there is probably a better way to do it.
  Additionally, I only do this on Linux; on Windows I leave CMake alone.
* Generating the API file is fragile, becuase it is not remotely C syntax
  aware; it's just dumb old sed.
* Do the right thing for 32/64 bit Python on Windows.
