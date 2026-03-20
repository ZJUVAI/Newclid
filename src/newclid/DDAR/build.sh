#!/usr/bin/env sh

set -e  # 任一命令失败就退出，避免后面用到错误结果

mkdir -p build
cd build

# 从当前 Python 环境自动获取 pybind11 的 CMake 配置目录
PYBIND11_DIR=$(python -m pybind11 --cmakedir)

echo "Using pybind11_DIR=${PYBIND11_DIR}"

cmake -DCMAKE_BUILD_TYPE=Release -Dpybind11_DIR="${PYBIND11_DIR}" ..

cmake --build .

cd ..