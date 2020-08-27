import os
from subprocess import check_call
import shutil
import sys

import setuptools.command.build_py
import setuptools.command.build_ext

# have to exec; can't import the package before it's built.
exec(open("pynng/_version.py", encoding="utf-8").read())

THIS_DIR = os.path.abspath(os.path.dirname(__file__))

NNG_REPO = 'https://github.com/nanomsg/nng'
NNG_REV = '4f5e11c391c4a8f1b2731aee5ad47bc0c925042a'
MBEDTLS_REPO = 'https://github.com/ARMmbed/mbedtls.git'
MBEDTLS_REV = '04a049bda1ceca48060b57bc4bcf5203ce591421'

WINDOWS = sys.platform == 'win32'


def _rmdir(dirname):
    # we can't use shutil.rmtree because it won't delete readonly files.
    if WINDOWS:
        cmd = ['rmdir', '/q', '/s', dirname]
    else:
        cmd = ['rm', '-rf', dirname]
    return check_call(cmd)


def build_mbedtls(cmake_args):
    """
    Clone mbedtls and build it with cmake.

    """
    do = check_call
    if os.path.exists('mbedtls'):
        _rmdir('mbedtls')
    do('git clone --recursive {}'.format(MBEDTLS_REPO), shell=True)
    # for local hacking, just copy a directory (network connection is slow)
    # do('cp -r ../mbedtls mbedtls', shell=True)
    do('git checkout {}'.format(MBEDTLS_REV), shell=True, cwd='mbedtls')
    cwd = 'mbedtls/build'
    os.mkdir(cwd)
    cmake_cmd = ['cmake'] + cmake_args
    cmake_cmd += [
        '-DENABLE_PROGRAMS=OFF',
        '-DCMAKE_BUILD_TYPE=Release',
        '-DCMAKE_INSTALL_PREFIX=../prefix',
        '..'
    ]
    print('building mbedtls with:', cmake_cmd)
    do(cmake_cmd, cwd=cwd)
    do(
        'cmake --build . --config Release --target install',
        shell=True,
        cwd=cwd,
    )


def build_nng(cmake_args):
    """
    Clone nng and build it with cmake, with TLS enabled.

    """
    do = check_call
    if os.path.exists('nng'):
        _rmdir('nng')
    do('git clone {}'.format(NNG_REPO), shell=True)
    # for local hacking, just copy a directory (network connection is slow)
    # do('cp -r ../nng-clean nng', shell=True)
    do('git checkout {}'.format(NNG_REV), shell=True, cwd='nng')
    os.mkdir('nng/build')
    cmake_cmd = ['cmake'] + cmake_args
    cmake_cmd += [
        '-DNNG_ENABLE_TLS=ON',
        '-DNNG_TESTS=OFF',
        '-DNNG_TOOLS=OFF',
        '-DCMAKE_BUILD_TYPE=Release',
        '-DMBEDTLS_ROOT_DIR={}/mbedtls/prefix/'.format(THIS_DIR),
        '..',
    ]
    print('building mbedtls with:', cmake_cmd)
    do(cmake_cmd, cwd='nng/build')
    do(
        'cmake --build . --config Release',
        shell=True,
        cwd='nng/build',
    )


def build_libs():
    """
    Builds the nng and mbedtls libs.

    """
    # The user has to have the correct Visual Studio version on the path or the
    # build will fail, possibly in exciting and mysterious ways.
    major, minor, *_ = sys.version_info

    flags = ['-DCMAKE_POSITION_INDEPENDENT_CODE:BOOL=true']
    is_64bit = sys.maxsize > 2**32
    if WINDOWS:
        if is_64bit:
            flags += ['-A', 'x64']
        else:
            flags += ['-A', 'win32']

    if shutil.which('ninja'):
        # the ninja build generator is a million times faster.
        flags += ['-G', 'Ninja']
    build_mbedtls(flags)
    build_nng(flags)


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

    build_libs()


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
