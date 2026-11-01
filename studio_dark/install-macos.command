#!/bin/bash
set -eu
SCRIPT_DIR="$(cd -- "$(dirname -- "$0")" && pwd)"
PYTHON_BIN="$(command -v python3 || true)"
if [ -z "$PYTHON_BIN" ] && [ -x "/Applications/Inkscape.app/Contents/Resources/bin/python3" ]; then
  PYTHON_BIN="/Applications/Inkscape.app/Contents/Resources/bin/python3"
fi
if [ -z "$PYTHON_BIN" ]; then
  echo "Python 3 was not found. Install Inkscape in /Applications, then try again."
  read -r -p "Press Enter to close... " _answer
  exit 1
fi
result=0
"$PYTHON_BIN" "$SCRIPT_DIR/install.py" install "$@" || result=$?
if [ -t 0 ]; then
  read -r -p "Press Enter to close... " _answer
fi
exit "$result"
