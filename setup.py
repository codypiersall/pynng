import os
from subprocess import check_call
import platform
import shutil
import sys

if platform.machine() == "i686" and platform.system() == "Linux":
    # mbedtls v3.5.1 will not build without these flags on 32-bit linux.
    # https://github.com/Mbed-TLS/mbedtls/issues/8334
    # this is hopefully going to be fixed in another release.
    # There is probably a better way to do this...
    os.environ["CFLAGS"] = "-mpclmul -msse2 -maes"
from setuptools import Command, setup, find_packages
from setuptools.command.build_ext import build_ext

WINDOWS = sys.platform == "win32"

THIS_DIR = os.path.abspath(os.path.dirname(__file__))


def maybe_copy(src, dst):
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    if os.path.exists(src):
        shutil.copy(src, dst)


class BuilderBase(Command):
    """Base Class for building vendored dependencies"""

    user_options = [
        ("repo=", None, "GitHub repository URL."),
        ("rev=", None, "GitHub repository revision."),
    ]

    flags = ["-DCMAKE_POSITION_INDEPENDENT_CODE:BOOL=true"]
    is_64bit = sys.maxsize > 2**32
    if WINDOWS:
        if is_64bit:
            flags += ["-A", "x64"]
        else:
            flags += ["-A", "win32"]
    else:
        if shutil.which("ninja"):
            print("~~~building with ninja~~~", file=sys.stderr)
            # the ninja build generator is a million times faster.
            flags += ["-G", "Ninja"]
        else:
            print("~~~building without ninja~~~", file=sys.stderr)

    cmake_cmd = ["cmake"] + flags

    def initialize_options(self):
        """Set default values for options."""
        self.repo = ""
        self.rev = ""

    def finalize_options(self):
        """Post-process options."""
        pass

    def run(self):
        """Clone nng and build it with cmake, with TLS enabled."""
        if not os.path.exists(self.git_dir):
            check_call("git clone {}".format(self.repo), shell=True)
            check_call("git checkout -f {}".format(self.rev), shell=True, cwd=self.git_dir)
        if not os.path.exists(self.build_dir):
            os.mkdir(self.build_dir)

        cmake_cmd = [*self.cmake_cmd, *self.cmake_extra_args, ".."]
        print(f"building {self.git_dir} with:", cmake_cmd, flush=True)
        check_call(cmake_cmd, cwd=self.build_dir)

        self.finalize_build()


class BuildNng(BuilderBase):
    description = "build the nng library"
    build_dir = "nng/build"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.git_dir = "nng"
        self.cmake_extra_args = [
            "-DNNG_ENABLE_TLS=ON",
            "-DNNG_TESTS=OFF",
            "-DNNG_TOOLS=OFF",
            "-DCMAKE_BUILD_TYPE=Release",
            "-DMBEDTLS_ROOT_DIR={}/mbedtls/prefix/".format(THIS_DIR),
        ]

    def finalize_build(self):
        check_call(
            "cmake --build . --config Release",
            shell=True,
            cwd=self.build_dir,
        )
        if WINDOWS:
            # Move ninja stuff to Release directory, so it is where the build_pynng script
            # expects.
            maybe_copy(f"nng/build/nng.lib", "nng/build/Release/nng.lib")


class BuildMbedTls(BuilderBase):
    description = "build the mbedtls library"
    build_dir = "mbedtls/build"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.git_dir = "mbedtls"
        self.cmake_extra_args = [
            "-DENABLE_PROGRAMS=OFF",
            "-DCMAKE_BUILD_TYPE=Release",
            "-DCMAKE_INSTALL_PREFIX=../prefix",
            "-DENABLE_TESTING=OFF",
        ]

    def finalize_build(self):
        check_call(
            "cmake --build . --config Release --target install",
            shell=True,
            cwd=self.build_dir,
        )
        if WINDOWS:
            # Move ninja stuff to Release directory, so it is where the build_pynng script
            # expects.
            src = "./mbedtls/build/library/"
            dst = "./mbedtls/build/library/Release/"
            maybe_copy(src + "mbedtls.lib", dst + "mbedtls.lib")
            maybe_copy(src + "mbedx509.lib", dst + "mbedx509.lib")
            maybe_copy(src + "mbedcrypto.lib", dst + "mbedcrypto.lib")
        else:
            # kinda hacky...
            # In CI, mbedtls installs its libraries into mbedtls/prefix/lib64.
            # Not totally sure when this happened, but something in mbedtls changed,
            # likely commit 0f2e87bdf534a967937882e7381e067d9b1cb135, when they started
            # using GnuInstallDirs. Couldn't build to verify but likely enough.
            src = f"{THIS_DIR}/mbedtls/prefix/lib64"
            dst = f"{THIS_DIR}/mbedtls/prefix/lib"
            if os.path.exists(src) and not os.path.exists(dst):
                shutil.copytree(src, dst)


class BuildBuild(build_ext):
    """
    Custom build command
    """

    def initialize_options(self):
        """
        Set default values for options
        Each user option must be listed here with their default value.
        """
        build_ext.initialize_options(self)

    def run(self):
        """
        Running...
        """
        self.run_command("build_mbedtls")
        self.run_command("build_nng")

        build_ext.run(self)  # proceed with "normal" build steps


with open("README.md", "r", encoding="utf-8") as f:
    long_description = f.read()

setup(
    cmdclass={
        "build_mbedtls": BuildMbedTls,
        "build_nng": BuildNng,
        "build_ext": BuildBuild,
    },
    cffi_modules=["build_pynng.py:ffibuilder"],
)
