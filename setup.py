import os
import shutil
import subprocess
import sys

import setuptools.command.build_py
import setuptools.command.build_ext

# have to exec; can't import the package before it's built.
exec(open("pynng/_version.py", encoding="utf-8").read())

THIS_DIR = os.path.dirname(__file__)

NNG_REVISION = 'd3bd35ab49ad74528fd9e34cce9016d74dd91943'
MBEDTLS_REVISION = '04a049bda1ceca48060b57bc4bcf5203ce591421'


def build_nng_lib():
    # cannot import build_pynng at the top level becuase cffi may not be
    # installed yet (since it is a dependency, and this script installs
    # dependencies).  Bootstrapping!
    import build_pynng
    if len(build_pynng.objects) > 0 and all(map(os.path.exists, build_pynng.objects)):
        # the object file we were planning on building already exists; we'll
        # just use it!
        return

    is_64bit = sys.maxsize > 2**32
    is_posix_shell = os.getenv("SHELL") is not None

    script = os.path.join(THIS_DIR, 'build_nng.sh') if is_posix_shell \
        else os.path.join(THIS_DIR, 'build_nng.bat')

    platform = ""
    if sys.platform == 'win32':
        platform = "-A x64" if is_64bit else "-A win32"

    cmd = [script, NNG_REVISION, MBEDTLS_REVISION, platform]

    if is_posix_shell:
        cmd = [shutil.which("sh")] + cmd

    subprocess.check_call(cmd)


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
    name='pynng-tls',
    version=__version__,
    author='Cody Piersall',
    author_email='cody.piersall@gmail.com',
    description='Networking made simply using nng (TLS enabled version)',
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
