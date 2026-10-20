#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -ne 1 ]; then
    printf 'Usage: %s <temporary-directory>\n' "$0" >&2
    exit 2
fi

script_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
remote=$(git -C "$script_dir" remote get-url origin)
temporary_root=$1
mkdir -p -- "$temporary_root"
run_dir=$(mktemp -d "${temporary_root%/}/rebuild.XXXXXXXX")
trap 'rm -rf -- "$run_dir"' EXIT
mkdir "$run_dir/tmp" "$run_dir/uv-cache"
export TMPDIR="$run_dir/tmp"
export UV_CACHE_DIR="$run_dir/uv-cache"

started=$SECONDS
git clone --quiet --depth 1 "$remote" "$run_dir/checkout"
cd "$run_dir/checkout"
uv venv --python 3.12 .venv
uv pip sync --python .venv/bin/python requirements.txt
uv pip check --python .venv/bin/python
PYTHONPATH=. .venv/bin/python -m unittest discover -s tests -q
.venv/bin/python fivech_back_up/thread_backup.py --help >/dev/null
.venv/bin/python -m scrapy list
bash -n gitpush.sh "$script_dir/scripts/rebuild_check.sh"
printf 'Rebuild check passed in %s seconds; checkout and environment: %s\n' \
    "$((SECONDS - started))" "$(du -sh . | cut -f1)"
