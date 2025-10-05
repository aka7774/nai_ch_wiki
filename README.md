# nai_ch_wiki

Automated backups for the nai_ch SeesaaWiki and the associated 5ch "nanJNVA" threads.

## Repository layout
- `back_up/` – latest SeesaaWiki page snapshots produced by the Scrapy crawler.
- `thread_back_up/` – stored 5ch thread exports (`json`／`txt`),手動取得した `dat/`、および状態ファイル。
- `seesawiki_back_up/` – Scrapy project that mirrors the wiki (`crawl.py` entry point).
- `fivech_back_up/thread_backup.py` – 5ch thread backup CLI used during the daily run.
- `gitpush.sh` – orchestrates the daily workflow, running both backup routines and pushing commits.
- `README_legacy.md` – original project handover notes kept for reference.

## Daily automation
`gitpush.sh` is executed every day at 05:30. The script performs the following steps:
1. Runs `venv/bin/python fivech_back_up/thread_backup.py daily` to update the 5ch archive.
2. Runs `venv/bin/python seesawiki_back_up/crawl.py backup` to mirror the wiki.
3. Commits and pushes only when new or changed files are detected.

If either backup command fails, the script aborts and nothing is committed.

## 5ch backup operations
The 5ch helper stores metadata in `thread_back_up/state.json` and tracks the current thread URL in `thread_back_up/latest_thread_url.txt`. Typical commands (run from the repo root with the virtualenv activated):

```bash
venv/bin/python fivech_back_up/thread_backup.py daily
venv/bin/python fivech_back_up/thread_backup.py daily --refetch
venv/bin/python fivech_back_up/thread_backup.py follow-prev <thread-url>
venv/bin/python fivech_back_up/thread_backup.py import-wiki <wiki-url> [...]
```

See `fivech_back_up/README.md` for detailed usage and one-off migration guidance.

## Initial setup checklist
- Ensure the Python virtualenv in `venv/` is available and contains `requests` and Scrapy dependencies.
- Update `thread_back_up/latest_thread_url.txt` whenever the community opens a brand new thread.
- Review `gitpush.sh` whenever adding new automated tasks so failures stop the daily job cleanly.

## Additional notes
- Historic wiki backup behaviour is unchanged; refer to `seesawiki_back_up/README.md` for crawler details.
- Avoid committing machine specific paths or secrets in documentation or state files.
