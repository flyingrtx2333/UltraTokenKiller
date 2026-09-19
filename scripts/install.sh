#!/usr/bin/env sh
set -eu
script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
source_dir=$(CDPATH= cd -- "$script_dir/.." && pwd)
utk_root="${XDG_STATE_HOME:-$HOME/.local/state}/utk"
python3 -m venv "$utk_root/venv"
"$utk_root/venv/bin/python" -m pip install --upgrade --constraint "$source_dir/constraints.txt" "$source_dir"
"$utk_root/venv/bin/python" -m ultratokenkiller.cli install
