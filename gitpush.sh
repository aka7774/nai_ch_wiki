#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")"

log() {
    printf '[%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S %z')" "$*"
}

PYTHON="venv/bin/python"
REQUIREMENTS_STAMP="venv/.requirements-installed"

if [ ! -x "$PYTHON" ]; then
    log "Python virtualenv is missing. Creating venv/."
    if ! command -v python3 >/dev/null 2>&1; then
        log "python3 is not available. Aborting."
        exit 1
    fi
    if ! python3 -m venv venv; then
        log "Failed to create venv/. Aborting."
        exit 1
    fi
fi

if [ ! -f "$REQUIREMENTS_STAMP" ] || [ requirements.txt -nt "$REQUIREMENTS_STAMP" ]; then
    log "Installing Python dependencies."
    if ! "$PYTHON" -m pip install --upgrade pip setuptools wheel; then
        log "Failed to upgrade Python packaging tools. Aborting."
        exit 1
    fi
    if ! "$PYTHON" -m pip install -r requirements.txt; then
        log "Failed to install requirements. Aborting."
        exit 1
    fi
    touch "$REQUIREMENTS_STAMP"
fi

log "Running 5ch thread backup."
if ! "$PYTHON" fivech_back_up/thread_backup.py daily; then
    log "5ch thread backup failed. Continuing with wiki backup."
    # exit 1
fi

log "Running SeesaaWiki backup."
if ! "$PYTHON" seesawiki_back_up/crawl.py backup; then
    log "Crawler failed. Aborting."
    exit 1
fi

if ! git status --porcelain back_up thread_back_up | grep -q "."; then
    log "No backup changes detected. Skipping commit."
    exit 0
fi

git add back_up thread_back_up

if git diff --cached --quiet; then
    log "No staged backup changes detected. Skipping commit."
    exit 0
fi

today=$(date "+%Y%m%d")
log "Committing backup changes."
git commit -m "Backup ${today}"
log "Pushing backup commit."
git push
log "Daily backup finished."
