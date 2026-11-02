#!/bin/bash
# User-level (no sudo) build toolchain for pokeemerald-expansion in WSL.
# Run via dev/setup_toolchain.ps1, which downloads the archives on the Windows
# side (this Debian image has no curl/wget) and passes their directory here.
# Installs into ~/.local: Arm GNU Toolchain (gcc + newlib) and Python 3 (uv).
# Alternative if you have sudo:
#   sudo apt install gcc-arm-none-eabi libnewlib-arm-none-eabi python3
set -euo pipefail
DL="${1:?usage: setup_toolchain.sh <download_dir>}"
ARM_DIR="$HOME/.local/arm-gnu-toolchain"
BIN="$HOME/.local/bin"
mkdir -p "$BIN" "$ARM_DIR"

if [ ! -x "$ARM_DIR/bin/arm-none-eabi-gcc" ]; then
  echo "Extracting Arm GNU Toolchain ..."
  tar -xJf "$DL/arm-none-eabi.tar.xz" -C "$ARM_DIR" --strip-components=1
fi

if [ ! -x "$BIN/python3" ]; then
  echo "Installing Python via uv ..."
  tmp=$(mktemp -d)
  tar -xzf "$DL/uv.tar.gz" -C "$tmp"
  cp "$tmp"/uv-*/uv "$tmp"/uv-*/uvx "$BIN/"
  rm -rf "$tmp"
  "$BIN/uv" python install 3.12
  ln -sf "$("$BIN/uv" python find 3.12)" "$BIN/python3"
fi

echo "--- toolchain ---"
"$ARM_DIR/bin/arm-none-eabi-gcc" --version | head -1
"$BIN/python3" --version
