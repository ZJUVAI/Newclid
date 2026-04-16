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
        try:
            self._build_ddar()
        except Exception as e:
            print(f"⚠️  DDAR build failed (continuing): {e}")
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
        # Resolve the real Python prefix (handles venv -> base Python)
        python_prefix = subprocess.check_output(
            [sys.executable, "-c",
             "import sys; print(getattr(sys, 'real_prefix', sys.base_prefix))"],
            text=True
        ).strip()

        python_include = subprocess.check_output(
            [sys.executable, "-c",
             "import sysconfig; print(sysconfig.get_path('include'))"],
            text=True, env={**os.environ, "PYTHONPATH": ""}
        ).strip()
        # If the include dir points inside a venv (no Python.h), resolve to base
        if not Path(python_include, "Python.h").exists():
            python_include = str(Path(python_prefix) / "include" / f"python{sys.version_info.major}.{sys.version_info.minor}")

        cmake_args = [
            f"-DCMAKE_BUILD_TYPE=Release",
            f"-Dpybind11_DIR={pybind11_cmake}",
            "-DCMAKE_POSITION_INDEPENDENT_CODE=ON",
            f"-DPython_EXECUTABLE={sys.executable}",
            f"-DPython_ROOT_DIR={python_prefix}",
            f"-DPython_INCLUDE_DIR={python_include}",
            "-DCMAKE_CUDA_FLAGS=-allow-unsupported-compiler",
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
    Pybind11Extension(
        "newclid.generation.auxiliary",
        [
            "src/newclid/generation/auxiliary/geometry.cpp",
            "src/newclid/generation/auxiliary/line.cpp",
            "src/newclid/generation/auxiliary/circle.cpp",
            "src/newclid/generation/auxiliary/utils.cpp",
            "src/newclid/generation/auxiliary/pybind.cpp",
        ],
        extra_compile_args=["-O3", "-std=c++17", "-march=native"],
    ),
]

setup(
    ext_modules=ext_modules,
    cmdclass={"build_ext": DDARBuildCommand},
)
