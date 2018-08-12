# Note: we instantiate the same 'cffi.FFI' class as in the previous
# example, but call the result 'ffibuilder' now instead of 'ffi';
# this is to avoid confusion with the other 'ffi' object you get below

from cffi import FFI
import subprocess
ffibuilder = FFI()

ffibuilder.set_source("_nng",
   r""" // passed to the real C compiler,
        // contains implementation of things declared in cdef()
        #include <nng.h>
        #include <protocol/pair1/pair.h>

    """,
    # libraries=['nng'],
    # library_dirs=['build',],
    # (more arguments like setup.py's Extension class:
    include_dirs=['nng/src'],
    extra_objects=['./nng/build/libnng.a'],
)

with open('nng_api.h') as f:
   api = f.read()
ffibuilder.cdef(api)

if __name__ == "__main__":
    ffibuilder.compile(verbose=True)
