#!/bin/zsh
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
SDK_ROOT="/Applications/Ultraleap Hand Tracking.app/Contents/LeapSDK"
BUILD_DIR="$ROOT_DIR/build"

mkdir -p "$BUILD_DIR"

clang -std=c11 -Wall -Wextra \
  -I"$SDK_ROOT/include" \
  "$ROOT_DIR/src/leap_stream_helper.c" \
  -L"$SDK_ROOT/lib" \
  -Wl,-rpath,"$SDK_ROOT/lib" \
  -lLeapC \
  -o "$BUILD_DIR/leap_stream_helper"
