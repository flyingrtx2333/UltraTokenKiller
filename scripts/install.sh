#!/usr/bin/env sh
set -eu

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
source_dir=$(CDPATH= cd -- "$script_dir/.." && pwd)
utk_root="${XDG_STATE_HOME:-$HOME/.local/state}/utk"
active="$utk_root/venv"
staging="$utk_root/venv.new"
previous="$utk_root/venv.previous"
mkdir -p "$utk_root"

case "$staging" in "$utk_root"/*) ;; *) echo "Unsafe staging path" >&2; exit 1;; esac
rm -rf "$staging"
python3 -m venv "$staging"
"$staging/bin/python" -m pip install --upgrade --constraint "$source_dir/constraints.txt" "$source_dir"
"$staging/bin/python" -m ultratokenkiller.cli capabilities >/dev/null
if [ "${UTK_SKIP_ASSETS:-0}" != "1" ]; then
  UTK_HOME="$utk_root" "$staging/bin/python" -m ultratokenkiller.cli assets install
fi

rm -rf "$previous"
if [ -d "$active" ]; then mv "$active" "$previous"; fi
mv "$staging" "$active"
if ! "$active/bin/python" -m ultratokenkiller.cli install; then
  rm -rf "$active"
  if [ -d "$previous" ]; then mv "$previous" "$active"; fi
  echo "UTK installation failed; previous runtime restored" >&2
  exit 1
fi
echo "UTK installed. Previous runtime retained at $previous for rollback."
