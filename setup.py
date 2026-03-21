import os
import subprocess
import sys
import sysconfig
import shutil
from pathlib import Path
from setuptools import setup, Extension
from setuptools.command.build_ext import build_ext
from setuptools.command.build import build
from pybind11.setup_helpers import Pybind11Extension, build_ext as pybind11_build_ext


class DDARBuildCommand(build_ext):
    """Custom build command to compile DDAR C++ module"""

    def build_extensions(self):
        """Compile DDAR before building Python extensions"""
        self._build_ddar()
        super().build_extensions()

    def _build_ddar(self):
        """Build DDAR using CMake"""
        ddar_dir = Path("src/newclid/DDAR")
        build_dir = ddar_dir / "build"

        if not ddar_dir.exists():
            print(f"⚠️  DDAR directory not found: {ddar_dir}")
            return

        print(f"🔨 Building DDAR C++ module...")

        # 1. Create build directory
        build_dir.mkdir(exist_ok=True)

        # 2. Get pybind11 CMake directory path
        try:
            pybind11_cmake = subprocess.check_output(
                [sys.executable, "-m", "pybind11", "--cmakedir"],
                text=True
            ).strip()
        except subprocess.CalledProcessError as e:
            print(f"❌ Failed to get pybind11 CMake path: {e}")
            raise

        # 3. Run CMake configuration
        cmake_args = [
            f"-DCMAKE_BUILD_TYPE=Release",
            f"-Dpybind11_DIR={pybind11_cmake}",
            "-DCMAKE_POSITION_INDEPENDENT_CODE=ON",
            f"-DPython_EXECUTABLE={sys.executable}",
        ]

        try:
            subprocess.run(
                ["cmake", ".."] + cmake_args,
                cwd=str(build_dir),
                check=True,
                capture_output=False,
            )
            print("✅ CMake configuration succeeded")
        except subprocess.CalledProcessError as e:
            print(f"❌ CMake configuration failed: {e}")
            raise
        except FileNotFoundError:
            print("❌ CMake not found. Please ensure CMake is installed")
            raise

        # 4. Build the project
        try:
            subprocess.run(
                ["cmake", "--build", "."],
                cwd=str(build_dir),
                check=True,
                capture_output=False,
            )
            print("✅ DDAR compilation succeeded")
        except subprocess.CalledProcessError as e:
            print(f"❌ DDAR compilation failed: {e}")
            raise


ext_modules = [
    Pybind11Extension(
        "newclid.dependencies.geometry",
        ["src/newclid/dependencies/geometry.cpp"],
        extra_compile_args=["-O3", "-std=c++14"],
    ),
    Pybind11Extension(
        "newclid.matchinC",
        ["src/newclid/matchinC.cpp"],
        extra_compile_args=["-O3", "-std=c++14"],
    ),
]

setup(
    ext_modules=ext_modules,
    cmdclass={"build_ext": DDARBuildCommand},
)
