#!/bin/bash
# Double-click this to open the SAP Load Workbench in your browser.
cd "$(dirname "$0")" || exit 1
if command -v python3 >/dev/null 2>&1; then
  exec python3 -m sapload.serve
fi
echo
echo "  Python 3 was not found. Install it from https://www.python.org/downloads/"
echo "  then double-click this file again."
echo
read -r -p "Press Enter to close."
