#!/bin/zsh
cd "$(dirname "$0")" || exit 1
if [[ ! -d .venv ]]; then
  echo "Python environment not found. Follow the setup steps in README.md first."
  read "REPLY?Press Enter to close: "
  exit 1
fi
source .venv/bin/activate
python music_hue.py
status=$?
echo
if [[ $status -ne 0 ]]; then
  echo "Program exited with status $status."
fi
read "REPLY?Press Enter to close this window: "
