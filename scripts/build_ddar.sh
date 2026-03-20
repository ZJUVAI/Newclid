#!/bin/bash
# Build both full and weak DDAR shared libraries.
#
# Usage:
#   bash scripts/build_ddar.sh          # build both
#   bash scripts/build_ddar.sh full     # build full only
#   bash scripts/build_ddar.sh weak     # build weak only

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
DDAR_DIR="$PROJECT_ROOT/src/newclid/DDAR"
PYBIND11_DIR="/usr/local/lib/python3.8/dist-packages/pybind11/share/cmake/pybind11"

TARGET="${1:-both}"

build_full() {
    echo "=== Building DDAR (full) ==="
    cmake -B "$DDAR_DIR/build" -S "$DDAR_DIR" -DDDAR_WEAK=OFF -Dpybind11_DIR="$PYBIND11_DIR"
    cmake --build "$DDAR_DIR/build" -j"$(nproc)"
    echo "  -> $(ls "$DDAR_DIR/build/"*.so 2>/dev/null || echo 'no .so found')"
}

build_weak() {
    echo "=== Building DDAR (weak) ==="
    cmake -B "$DDAR_DIR/build_weak" -S "$DDAR_DIR" -DDDAR_WEAK=ON -Dpybind11_DIR="$PYBIND11_DIR"
    cmake --build "$DDAR_DIR/build_weak" -j"$(nproc)"
    echo "  -> $(ls "$DDAR_DIR/build_weak/"*.so 2>/dev/null || echo 'no .so found')"
}

case "$TARGET" in
    full)  build_full ;;
    weak)  build_weak ;;
    both)  build_full; build_weak ;;
    *)     echo "Usage: $0 [full|weak|both]"; exit 1 ;;
esac

echo "=== Build complete ==="
