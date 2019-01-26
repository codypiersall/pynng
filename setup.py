import os
import shutil
import subprocess
import sys

import setuptools.command.build_py
import setuptools.command.build_ext


THIS_DIR = os.path.dirname(__file__)


NNG_REVISION = 'd3bd35ab49ad74528fd9e34cce9016d74dd91943'


def build_nng_lib():
    # cannot import build_pynng at the top level becuase cffi may not be
    # installed yet (since it is a dependency, and this script installs
    # dependencies).  Bootstrapping!
    import build_pynng
    if os.path.exists(build_pynng.objects[0]):
        # the object file we were planning on building already exists; we'll
        # just use it!
        return
    if sys.platform == 'win32':
        is_64bit = sys.maxsize > 2**32
        major, minor, *_ = sys.version_info
        build_nng_script = os.path.join(THIS_DIR, 'build_nng.bat')
        needs_shell = True
        # pick the correct cmake generator, based on the Python version.
        # from https://wiki.python.org/moin/WindowsCompilers for Python
        # version, and cmake --help for list of CMake generator names

        # If ninja build system is installed, use it, since it's way faster
        # (this is especially important when feeling impatient for CI builds)
        if shutil.which('ninja') and (major, minor) in ((3, 5), (3, 6), (3, 7)):
            # gotta soruce the correct vcvarsall!
            which_vcvars = {
                (3, 5): r'Microsoft Visual Studio 14.0\VC',
                (3, 6): r'Microsoft Visual Studio 14.0\VC',
                (3, 7): r'Microsoft Visual Studio 14.0\VC',
            }
            vcvarsall = os.path.join(
                r'C:\Program Files (x86)',
                which_vcvars[(major, minor)],
                'vcvarsall.bat',
            )
            if is_64bit:
                gen = 'amd64'
            else:
                gen = 'x86'
            cmd = '"{}" {} && {} Ninja {}'.format(vcvarsall, gen, build_nng_script, NNG_REVISION)
            print('-------------------')
            print(cmd)
            print('-------------------')

        else:
            cmake_generators = {
                (3, 5): 'Visual Studio 14 2015',
                (3, 6): 'Visual Studio 14 2015',
                (3, 7): 'Visual Studio 14 2015',
            }
            gen = cmake_generators[(major, minor)]

            if is_64bit:
                gen += ' Win64'

            cmd = [build_nng_script, gen, NNG_REVISION]

    else:
        # on Linux, build_nng.sh selects ninja if available
        script = os.path.join(THIS_DIR, 'build_nng.sh')
        cmd = ['/bin/bash', script, NNG_REVISION]
        needs_shell = False

    # shell=True is required for Windows
    subprocess.check_call(cmd, shell=needs_shell)


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
    'pytest-trio',
    'trio',
]

setuptools.setup(
    cmdclass={
        'build_py': BuildPyCommand,
        'build_ext': BuildExtCommand,
    },
    name='pynng',
    version='0.3.0',
    author='Cody Piersall',
    author_email='cody.piersall@gmail.com',
    description='Networking made simply using nng',
    long_description=long_description,
    license='MIT',
    keywords='networking nng nanomsg zmq messaging message',
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

