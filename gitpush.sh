#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")"

log() {
    printf '[%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S %z')" "$*"
}

VENV_DIR=".venv"
PYTHON="$VENV_DIR/bin/python"
backup_degraded=0

if [ ! -x "$PYTHON" ]; then
    log "Python virtualenv is missing. Creating $VENV_DIR with uv."
    if ! command -v uv >/dev/null 2>&1; then
        log "uv is not available. Aborting."
        exit 1
    fi
    if ! uv venv --python 3.12 "$VENV_DIR"; then
        log "Failed to create $VENV_DIR. Aborting."
        exit 1
    fi
fi

log "Synchronizing pinned Python dependencies with uv."
if ! uv pip sync --python "$PYTHON" requirements.txt; then
    log "Failed to synchronize requirements. Aborting."
    exit 1
fi

log "Running local regression tests."
if ! PYTHONPATH=. "$PYTHON" -m unittest discover -s tests -q; then
    log "Regression tests failed. Aborting before network backup."
    exit 1
fi

finish() {
    if [ "$backup_degraded" -ne 0 ]; then
        log "Daily backup completed in degraded state: 5ch backup failed."
        exit 2
    fi
    log "Daily backup finished."
}

log "Running 5ch thread backup."
if ! "$PYTHON" fivech_back_up/thread_backup.py daily; then
    log "5ch thread backup failed. Continuing with wiki backup."
    backup_degraded=1
fi

log "Running SeesaaWiki backup."
if ! "$PYTHON" seesawiki_back_up/crawl.py backup; then
    log "Crawler failed. Aborting."
    exit 1
fi

if ! git status --porcelain back_up thread_back_up | grep -q "."; then
    log "No backup changes detected. Skipping commit."
    finish
fi

git add back_up thread_back_up

if git diff --cached --quiet; then
    log "No staged backup changes detected. Skipping commit."
    finish
fi

today=$(date "+%Y%m%d")
log "Committing backup changes."
git commit -m "Backup ${today}"
log "Pushing backup commit."
git push
finish
