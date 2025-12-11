mkdir -p build
cd build
PYBIND11_DIR=$(python -m pybind11 --cmakedir)
cmake -DCMAKE_BUILD_TYPE=Release -Dpybind11_DIR="${PYBIND11_DIR}" ..
cmake --build .
cd ..