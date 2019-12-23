import os
import shutil
from subprocess import check_call
import sys

import setuptools.command.build_py
import setuptools.command.build_ext

# have to exec; can't import the package before it's built.
exec(open("pynng/_version.py", encoding="utf-8").read())

THIS_DIR = os.path.abspath(os.path.dirname(__file__))

NNG_REPO = 'https://github.com/nanomsg/nng'
NNG_REV = 'd3bd35ab49ad74528fd9e34cce9016d74dd91943'
MBEDTLS_REPO = 'https://github.com/ARMmbed/mbedtls.git'
MBEDTLS_REV = '04a049bda1ceca48060b57bc4bcf5203ce591421'


def build_mbedtls_windows(cmake_args):
    """
    Clone mbedtls and build it with cmake.

    """
    do = check_call
    if os.path.exists('mbedtls'):
        pass
        # we can't use shutil.rmtree because it won't delete readonly stuff.
        do('rmdir /q /s mbedtls', shell=True)
    do('git clone --recursive {}'.format(MBEDTLS_REPO), shell=True)
    do('git checkout {}'.format(MBEDTLS_REV), shell=True, cwd='mbedtls')
    os.mkdir('mbedtls/build')
    cmake_cmd = ['cmake'] + cmake_args
    cmake_cmd += [
        '-DENABLE_PROGRAMS=OFF',
        '-DCMAKE_BUILD_TYPE=Release',
        '-DCMAKE_INSTALL_PREFIX=..\prefix',
        '..'
    ]
    do(cmake_cmd, cwd='mbedtls/build')
    do(
        'cmake --build . --config Release',
        shell=True,
        cwd='mbedtls/build',
    )


def build_nng_windows(cmake_args):
    """
    Clone nng and build it with cmake, with TLS enabled.

    """
    do = check_call
    if os.path.exists('nng'):
        do('rmdir /q /s nng', shell=True)
    do('git clone {}'.format(NNG_REPO), shell=True)
    do('git checkout {}'.format(NNG_REV), shell=True, cwd='nng')
    os.mkdir('nng/build')
    cmake_cmd = ['cmake'] + cmake_args
    cmake_cmd += [
        '-DNNG_ENABLE_TLS=ON',
        '-DNNG_TESTS=OFF',
        '-DNNG_TOOLS=OFF',
        '-DCMAKE_BUILD_TYPE=Release',
        '-DMBEDTLS_ROOT_DIR={}/mbedtls/build/library/Release/'.format(THIS_DIR),
        '-DMBEDTLS_INCLUDE_DIR={}/mbedtls/include/'.format(THIS_DIR),
        '..',
    ]
    do(cmake_cmd, cwd='nng/build')
    do(
        'cmake --build . --config Release',
        shell=True,
        cwd='nng/build',
    )


def build_windows_libs():
    """
    Builds the nng and mbedtls libs.

    """
    # pick the correct cmake generator, based on the Python version.
    # from https://wiki.python.org/moin/WindowsCompilers for Python
    # version, and cmake --help for list of CMake generator names.
    # We can't *just* specify the architecture of Python because it could use
    # an incompatible compiler, i.e. there is no guarantee that VS 2017 will be
    # compatible with a VS 2015 build of Python.
    major, minor, *_ = sys.version_info
    cmake_generators = {
        (3, 5): 'Visual Studio 14 2015',
        (3, 6): 'Visual Studio 14 2015',
        (3, 7): 'Visual Studio 14 2015',
    }
    gen = cmake_generators[(major, minor)]

    is_64bit = sys.maxsize > 2**32
    if is_64bit:
        gen += ' Win64'

    build_mbedtls_windows(['-G', gen])
    build_nng_windows(['-G', gen])

def build_nng_lib():
    # cannot import build_pynng at the top level becuase cffi may not be
    # installed yet (since it is a dependency, and this script installs
    # dependencies).  Bootstrapping!
    import build_pynng
    objs = build_pynng.objects
    if objs and all(os.path.exists(p) for p in objs):
        # the object file we were planning on building already exists; we'll
        # just use it!
        return

    if sys.platform == 'win32':
        build_windows_libs()
    else:
        script = os.path.join(THIS_DIR, 'build_nng.sh')
        cmd = [shutil.which("sh"), script, NNG_REV, MBEDTLS_REV]
        check_call(cmd)


# TODO: this is basically a hack to get something to run before running cffi
# extnsion builder. subclassing something else would be better!
class BuildPyCommand(setuptools.command.build_py.build_py):
    """Build nng library before anything else."""

    def run(self):
        build_nng_lib()
        super(BuildPyCommand, self).run()


class BuildExtCommand(setuptools.command.build_ext.build_ext):
    """Build nng library before anything else."""

    def run(self):
        build_nng_lib()
        super(BuildExtCommand, self).run()


with open('README.md', 'r', encoding='utf-8') as f:
    long_description = f.read()

tests_require = [
    'pytest',
    'pytest-asyncio',
    'pytest-trio',
    'trio',
]

setuptools.setup(
    cmdclass={
        'build_py': BuildPyCommand,
        'build_ext': BuildExtCommand,
    },
    name='pynng',
    version=__version__,
    author='Cody Piersall',
    author_email='cody.piersall@gmail.com',
    description='Networking made simply using nng',
    long_description=long_description,
    license='MIT',
    keywords='networking nng nanomsg zmq messaging message trio asyncio',
    long_description_content_type='text/markdown',
    url='https://github.com/codypiersall/pynng',
    packages=setuptools.find_packages(),
    classifiers=([
        'Development Status :: 3 - Alpha',
        'Framework :: AsyncIO',
        'Framework :: Trio',
        'License :: OSI Approved :: MIT License',
        'Operating System :: OS Independent',
        'Programming Language :: Python :: 3 :: Only',
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7',
        'Programming Language :: Python :: 3.8',
        'Topic :: Software Development :: Libraries',
        'Topic :: System :: Networking',
    ]),
    setup_requires=['cffi', 'pytest-runner'],
    install_requires=['cffi', 'sniffio'],
    cffi_modules=['build_pynng.py:ffibuilder'],
    tests_require=tests_require,
    test_suite='tests',

)
