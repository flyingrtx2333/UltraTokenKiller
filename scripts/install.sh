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
python_ok() {
  "$1" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)' >/dev/null 2>&1
}

python_cmd=""
for candidate in python3.11 python3; do
  if command -v "$candidate" >/dev/null 2>&1 && python_ok "$candidate"; then
    python_cmd="$candidate"
    break
  fi
done

if [ -n "$python_cmd" ]; then
  "$python_cmd" -m venv "$staging"
else
 uv_bin=""
 # An explicit offline archive is authoritative, which also makes its digest
 # verification deterministic on hosts that already have uv installed.
 if [ -z "${UTK_UV_ARCHIVE:-}" ]; then
 uv_bin=$(command -v uv 2>/dev/null || true)
 if [ -z "$uv_bin" ]; then
 for candidate in /opt/homebrew/bin/uv /usr/local/bin/uv "$HOME/.local/bin/uv"; do
 if [ -x "$candidate" ]; then uv_bin="$candidate"; break; fi
 done
 fi
 fi
  if [ -z "$uv_bin" ]; then
    uv_version="0.12.17"
    machine=$(uname -m)
    system=$(uname -s)
    case "$system:$machine" in
      Darwin:arm64) asset="uv-aarch64-apple-darwin.tar.gz"; expected="85f00cbdc6dd3e97eba4c31b4d014375a9fdfe8f570023b84e5102fc3456896b" ;;
      Darwin:x86_64) asset="uv-x86_64-apple-darwin.tar.gz"; expected="8dcf05a8c809bb3c471d2b614788ba27a6e41298fc8c31ac84b5f4339fd468e5" ;;
      Linux:aarch64|Linux:arm64) asset="uv-aarch64-unknown-linux-gnu.tar.gz"; expected="d636d1b678e9e7f367ecb22b46bd1cabbed234d6bc3b4d96365d2b507f72f86c" ;;
      Linux:x86_64) asset="uv-x86_64-unknown-linux-gnu.tar.gz"; expected="fa82fd8dde8e8eefdecada6aa0889666556cfceb690d06e0c3bca49eb3070a63" ;;
      *) echo "Unsupported runtime bootstrap platform: $system $machine" >&2; exit 1 ;;
    esac
    bootstrap="$utk_root/runtime-bootstrap"
    archive="$bootstrap/$asset"
    mkdir -p "$bootstrap"
    if [ -n "${UTK_UV_ARCHIVE:-}" ]; then
      cp "$UTK_UV_ARCHIVE" "$archive"
      expected="${UTK_UV_SHA256:-$expected}"
    else
      command -v curl >/dev/null 2>&1 || { echo "curl is required to download the pinned runtime helper" >&2; exit 1; }
      curl -fL --retry 3 "https://github.com/astral-sh/uv/releases/download/$uv_version/$asset" -o "$archive"
    fi
    if command -v sha256sum >/dev/null 2>&1; then
      actual=$(sha256sum "$archive" | awk '{print $1}')
    else
      actual=$(shasum -a 256 "$archive" | awk '{print $1}')
    fi
    [ "$actual" = "$expected" ] || { echo "Runtime helper checksum mismatch" >&2; exit 1; }
    tar -xzf "$archive" -C "$bootstrap"
    uv_bin="$bootstrap/${asset%.tar.gz}/uv"
    [ -x "$uv_bin" ] || { echo "Pinned runtime helper is incomplete" >&2; exit 1; }
  fi
  "$uv_bin" venv --python 3.11 --seed "$staging"
fi
"$staging/bin/python" -m pip install --upgrade --constraint "$source_dir/constraints.txt" "$source_dir"
"$staging/bin/python" -m ultratokenkiller.cli capabilities >/dev/null
if [ "${UTK_SKIP_ASSETS:-0}" != "1" ]; then
  UTK_HOME="$utk_root" "$staging/bin/python" -m ultratokenkiller.cli assets install
fi

rm -rf "$previous"
if [ -d "$active" ]; then mv "$active" "$previous"; fi
mv "$staging" "$active"

# Virtual-environment console scripts embed the absolute interpreter path. The
# staging directory is renamed for an atomic switch, so repair only shebangs
# that still point at that staging directory before running health checks.
"$active/bin/python" - "$active/bin" "$staging" "$active" <<'PY'
from pathlib import Path
import sys

bin_dir = Path(sys.argv[1])
old_prefix = b"#!" + sys.argv[2].encode() + b"/"
new_prefix = b"#!" + sys.argv[3].encode() + b"/"
for launcher in bin_dir.iterdir():
    if not launcher.is_file():
        continue
    data = launcher.read_bytes()
    if data.startswith(old_prefix):
        launcher.write_bytes(new_prefix + data[len(old_prefix):])
PY
set --
if [ "${UTK_INSTALL_NO_CLIENTS:-0}" = "1" ]; then set -- "$@" --no-clients; fi
if [ "${UTK_INSTALL_NO_AUTOSTART:-0}" = "1" ]; then set -- "$@" --no-autostart; fi
if ! UTK_HOME="$utk_root" "$active/bin/python" -m ultratokenkiller.cli install "$@"; then
  rm -rf "$active"
  if [ -d "$previous" ]; then mv "$previous" "$active"; fi
  echo "UTK installation failed; previous runtime restored" >&2
  exit 1
fi
echo "UTK installed. Previous runtime retained at $previous for rollback."
