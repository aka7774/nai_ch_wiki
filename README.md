# nai_ch_wiki

Automated backups for the nai_ch SeesaaWiki and the associated 5ch "nanJNVA" threads.

## Repository layout
- `back_up_html/` – latest SeesaaWiki page bodies (rendered HTML) produced by the Scrapy crawler.
- `back_up/` – SeesaaWiki page source text as last retrievable (2026-04-07); no longer updated.
- `thread_back_up/` – stored 5ch thread exports (`json`／`txt`),手動取得した `dat/`、および状態ファイル。
- `seesawiki_back_up/` – Scrapy project that mirrors the wiki (`crawl.py` entry point).
- `fivech_back_up/thread_backup.py` – 5ch thread backup CLI used during the daily run.
- `gitpush.sh` – orchestrates the daily workflow, running both backup routines and pushing commits.
- `README_legacy.md` – original project handover notes kept for reference.

## Daily automation
`gitpush.sh` is run daily by an externally configured scheduler; the schedule and log destination are not stored in this repository. The script performs the following steps:
1. Ensures the uv-managed Python 3.12 virtualenv in `.venv/` exists and exactly synchronizes the lock in `requirements.txt`.
2. Runs the local regression tests before making network requests.
3. Runs `.venv/bin/python fivech_back_up/thread_backup.py daily` to update the 5ch archive.
4. Runs `.venv/bin/python seesawiki_back_up/crawl.py backup` to mirror the wiki into `back_up_html/`.
5. Commits and pushes only when `back_up_html/` or `thread_back_up/` changed.

If the wiki crawler fails, including a run that saves zero wiki pages, the script aborts and nothing is committed. If the 5ch backup fails, the wiki backup still runs and may be committed, but the overall command exits with status 2 so cron/monitoring cannot mistake the partial result for full success.

### Wiki collection route (2026-10-21)
SeesaaWiki's robots.txt now disallows the page list (`/*/l/`) and editor (`/*/e/`) URLs from which the crawler read each page's source text. The Wayback Machine copy of 2025-09-02 did not disallow them, and the source text in `back_up/` stops at 2026-04-07 although the wiki kept being edited, so the change most likely took effect in April 2026; the start URL and User-Agent did not change. Because the crawler obeys robots.txt, it saved nothing from then on: the daily run still reported success until 2026-07-25, the 2026-07-26 Scrapy update then kept the spider from starting at all, and once that was fixed on 2026-10-14 every run failed with `robotstxt/forbidden` (from 2026-10-15). SeesaaWiki offers readers no export or API, so the crawler now starts from the top page and the RSS feed (`site.rdf`), follows links to article pages (`/nai_ch/d/…`, which robots.txt allows) and saves each page's rendered body (`div.user-area`) as UTF-8 HTML in `back_up_html/<title>.html`; `ROBOTSTXT_OBEY` stays `True`. `back_up/` keeps the 2026-04-07 source text for tools that parse wiki markup. Pages that no collected page links to and that are not among the latest RSS items are not collected.

## 5ch backup operations
The 5ch helper stores metadata in `thread_back_up/state.json` and tracks the current thread URL in `thread_back_up/latest_thread_url.txt`. Typical commands (run from the repo root with the virtualenv activated):

```bash
.venv/bin/python fivech_back_up/thread_backup.py daily
.venv/bin/python fivech_back_up/thread_backup.py daily --refetch
.venv/bin/python fivech_back_up/thread_backup.py follow-prev <thread-url>
.venv/bin/python fivech_back_up/thread_backup.py import-wiki <wiki-url> [...]
```

See `fivech_back_up/README.md` for detailed usage and one-off migration guidance.

## Initial setup checklist
- Ensure `uv` and Python 3.12 are available; `gitpush.sh` creates `.venv/` and synchronizes the committed lock when needed.
- Update `thread_back_up/latest_thread_url.txt` whenever the community opens a brand new thread.
- Review `gitpush.sh` whenever adding new automated tasks so failures stop the daily job cleanly.

## Additional notes
- Refer to `seesawiki_back_up/README.md` for crawler details, failure detection, and bounded live checks.
- Avoid committing machine specific paths or secrets in documentation or state files.

## 作り直す

### Prerequisites and installation

Use Linux (or WSL), Git, Bash, `uv`, and Python 3.12. The verified toolchain is
Python 3.12.3 and uv 0.9.18; all 37 Python packages are pinned in
`requirements.txt`. Network access is
needed to install the pinned dependencies; collection additionally needs access
to the source sites. Install Git/uv using their supported installation methods.
Choose the checkout location according to your storage policy.

```bash
git clone https://github.com/aka7774/nai_ch_wiki.git
cd nai_ch_wiki
uv venv --python 3.12 .venv
uv pip sync --python .venv/bin/python requirements.txt
uv pip check --python .venv/bin/python
```

`requirements.txt` is the committed dependency lock. Do not copy an old virtual
environment. The historical `venv/` paths in older instructions are superseded
by `.venv/` for the daily workflow.

### Verify without collecting or publishing

Set `TMPDIR` to an existing, writable temporary directory allowed by your local
storage policy. Run these commands from the checkout root:

```bash
PYTHONPATH=. .venv/bin/python -m unittest discover -s tests -q
.venv/bin/python fivech_back_up/thread_backup.py --help
.venv/bin/python -m scrapy list
bash -n gitpush.sh
```

To repeat this check from an existing checkout, run
`bash scripts/rebuild_check.sh <temporary-directory>`. It clones `origin` into
a newly created subdirectory, installs the locked environment, runs the offline
checks above, prints elapsed time and checkout size, then deletes only that
subdirectory, including on failure. Give it a temporary location with enough
space for the checkout and packages. It never runs the collection or push job.

The regression suite uses temporary data and mocked network responses. The
Scrapy command should list `backup`; it loads the crawler without fetching
pages. The thread CLI with no command defaults to `daily`, so always include
`--help` for a read-only startup check.

### Restore data and resume the daily job

A full clone restores the committed `back_up/`, `back_up_html/` and `thread_back_up/` snapshots.
Recover any newer, uncommitted files from the previous installation before
resuming collection, while its collector is not writing. Preserve the thread
state, current-thread URL, JSON/TXT exports, manual DAT files, and CSV index
as one data set. Historical log files are optional for collection. Avoid
running collectors from two checkouts against the same data.

The current daily script stages and publishes both data directories through
Git. Replacing them with external-directory symlinks does **not** preserve
this publication workflow: Git records the links, not their contents. External
data storage requires a coordinated change to the collector and publication
workflow before removing the tracked snapshots.

For automatic publication, configure an authorized writable Git remote and
commit identity locally, and provision SSH authentication separately if that
remote requires it. Keep credentials out of tracked files. The HTTPS clone
above is sufficient for installation and local tests, but does not configure
unattended push authentication.

After restoring data and confirming the publication destination, `bash
gitpush.sh` performs a real collection, commit, and push. It is not a dry run.
Register that command in the new machine's scheduler with the absolute checkout
path, a PATH that resolves `uv` (or one of the fallback locations in the script),
and a log destination appropriate to the machine. Carry over the intended
schedule and timezone from the previous scheduler; cloning does not restore
cron. Do not overlap runs. Check the exit status and log: a thread-backup
failure can still publish the wiki backup but exits with status 2.

### Verification coverage

A fresh origin clone with Python 3.12.3 and a newly created environment passed
locked dependency installation, dependency checks, all 20 regression tests,
thread CLI help, crawler discovery, and shell syntax checks. Archived data was
checked out but was not read by these checks. Live source retrieval, restoration of unpublished
data, scheduler registration, and automatic Git publication were not exercised.
These checks therefore verify the local rebuild, not successful live collection.

### Moving to one PC

- `C:\data\akari`: no required data for this repository; the tracked `back_up/`
  and `thread_back_up/` directories come from the clone. If a previous run has
  unpublished changes, recover them before starting the new collector.
- `~/akari-data`: no persistent dependency. Provide only a writable temporary
  directory for the rebuild check and tests.
- Scheduler: recreate the external daily cron or equivalent entry for
  `gitpush.sh`, with its absolute checkout path, local timezone, and log
  destination. The original schedule is not recorded here.
- Resident services: none. A writable Git remote, commit identity, and SSH
  authentication are needed only for unattended publication.

On 2026-10-20 JST, `rebuild_check.sh` took 38 seconds and used 910 MB for the
shallow clone and new environment. No model or multi-GB dependency download is
required. Skipped checks and what they need:

- Live wiki and 5ch collection: source-site access and permission to update snapshots.
- Unattended Git publication: configured remote authentication and scheduler.
- Restoration of unpublished data: files from the previous installation.
