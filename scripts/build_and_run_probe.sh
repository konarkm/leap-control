#!/bin/zsh
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
BUILD_DIR="$ROOT_DIR/build"
SDK_ROOT="/Applications/Ultraleap Hand Tracking.app/Contents/LeapSDK"

mkdir -p "$BUILD_DIR"

if command -v cmake >/dev/null 2>&1; then
  cd "$BUILD_DIR"
  cmake ..
  cmake --build .
else
  clang -std=c11 -Wall -Wextra \
    -I"$SDK_ROOT/include" \
    "$ROOT_DIR/src/main.c" \
    -L"$SDK_ROOT/lib" \
    -Wl,-rpath,"$SDK_ROOT/lib" \
    -lLeapC \
    -framework CoreFoundation \
    -o "$BUILD_DIR/leap_probe"
fi

exec "$BUILD_DIR/leap_probe"
