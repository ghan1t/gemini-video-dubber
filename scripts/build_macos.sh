#!/usr/bin/env bash
set -euo pipefail

source .venv/bin/activate
pyinstaller pyinstaller/macos.spec --clean --noconfirm
