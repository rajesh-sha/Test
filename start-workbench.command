#!/bin/bash
# Double-click this to open the SAP Load Workbench in your browser.
# If macOS refuses to run it, right-click the file and choose Open.
cd "$(dirname "$0")" || exit 1
if ! command -v python3 >/dev/null 2>&1; then
  echo
  echo "  Python 3 was not found."
  echo "  Install it from https://www.python.org/downloads/ then try again."
  echo
  read -r -p "Press Enter to close."
  exit 1
fi
python3 -m sapload.serve || {
  echo
  echo "  The workbench did not start. Running the self check..."
  echo
  python3 check.py
  read -r -p "Press Enter to close."
}
