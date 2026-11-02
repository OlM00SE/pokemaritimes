#!/bin/bash
# Build the ROM with the user-level toolchain from dev/setup_toolchain.ps1.
# From Windows:  wsl -d Debian --cd <repo> -- bash dev/build.sh [make args]
set -eo pipefail
export PATH="$HOME/.local/arm-gnu-toolchain/bin:$HOME/.local/bin:$PATH"
cd "$(dirname "$0")/.."
start=$(date +%s)
make -j"$(nproc)" "$@"
echo "BUILD OK in $(( $(date +%s) - start ))s"
