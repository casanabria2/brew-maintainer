#!/bin/bash
set -e

echo "Installing brew-maintainer..."

# Check for Homebrew
if ! command -v brew &>/dev/null; then
    echo "Error: Homebrew is not installed. Install it from https://brew.sh"
    exit 1
fi

# Install pipx if needed
if ! command -v pipx &>/dev/null; then
    echo "Installing pipx..."
    brew install pipx
    pipx ensurepath
fi

# Install brew-maintainer
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
echo "Installing from ${SCRIPT_DIR}..."
pipx install -e "$SCRIPT_DIR"

echo ""
echo "Done! Open a new terminal, then run:"
echo "  brew-maintainer --help"
