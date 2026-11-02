#!/bin/bash
# User-level (no sudo) build toolchain for pokeemerald-expansion in WSL.
# Installs: Arm GNU Toolchain (arm-none-eabi gcc + newlib) and Python 3 (via uv)
# into ~/.local. Safe to re-run. The alternative, if you have sudo:
#   sudo apt install gcc-arm-none-eabi libnewlib-arm-none-eabi python3
set -euo pipefail
ARM_VER=14.2.rel1
ARM_DIR="$HOME/.local/arm-gnu-toolchain"
BIN="$HOME/.local/bin"
mkdir -p "$BIN" "$ARM_DIR"
dl() { if command -v curl >/dev/null; then curl -fsSL "$1" -o "$2"; else wget -q "$1" -O "$2"; fi; }

if [ ! -x "$ARM_DIR/bin/arm-none-eabi-gcc" ]; then
  echo "Downloading Arm GNU Toolchain $ARM_VER ..."
  tmp=$(mktemp -d)
  dl "https://developer.arm.com/-/media/Files/downloads/gnu/$ARM_VER/binrel/arm-gnu-toolchain-$ARM_VER-x86_64-arm-none-eabi.tar.xz" "$tmp/arm.tar.xz"
  tar -xJf "$tmp/arm.tar.xz" -C "$ARM_DIR" --strip-components=1
  rm -rf "$tmp"
fi

if [ ! -x "$BIN/python3" ]; then
  echo "Installing Python via uv ..."
  if ! command -v uv >/dev/null && [ ! -x "$BIN/uv" ]; then
    tmp=$(mktemp -d)
    dl "https://github.com/astral-sh/uv/releases/latest/download/uv-x86_64-unknown-linux-gnu.tar.gz" "$tmp/uv.tgz"
    tar -xzf "$tmp/uv.tgz" -C "$tmp"
    cp "$tmp"/uv-*/uv "$tmp"/uv-*/uvx "$BIN/"
    rm -rf "$tmp"
  fi
  "$BIN/uv" python install 3.12
  ln -sf "$("$BIN/uv" python find 3.12)" "$BIN/python3"
fi

echo "--- toolchain ---"
"$ARM_DIR/bin/arm-none-eabi-gcc" --version | head -1
"$BIN/python3" --version
