# 5ch thread backup CLI

`thread_backup.py` automates archiving of the "nanJNVA" 5ch threads. It mirrors the smartphone API output (`json`) and a readable text export while keeping track of thread progression。HTTPアクセスにはCloudflare対策として `cloudscraper` を使用します。

## Key features
- Downloads the full thread payload via the itest mobile API and stores it as JSON and TXT.
- Normalises itest/mobile URLs to their desktop equivalents and deduplicates threads.
- Tracks metadata (thread number, last fetch timestamp, post count, previous/next links) in `thread_back_up/state.json`.
- Stops refetching threads automatically once they reach 1000 posts (with `--refetch` available when needed).
- When the active thread reaches 950 posts, searches `find.5ch.net` for successor threads and archives both the old and new threads in the same run.
- Writes a combined index of thread numbers and URLs to `thread_back_up/thread_urls.csv` on every run.
  - 行構成は `number,status,posts,title,url,first_post_at,remark` です。欠番が判明した場合は `status=missing` の行が追加され、手動取得した `.dat` 由来のスレには `remark` で出典を明記します。

## Files and directories
- `thread_back_up/json/` – raw API responses (`<number>_<slug>.json`).
- `thread_back_up/txt/` – human-readable exports matching the JSON filenames.
- `thread_back_up/state.json` – persisted metadata for each known thread。
- `thread_back_up/latest_thread_url.txt` – canonical URL for the current live thread。
- `thread_back_up/dat/` – 公式APIから取得できなくなったスレの手動バックアップ（n2ch等から復元した`.dat`）。

## Daily execution
The `daily` command powers the scheduled job (see `gitpush.sh`). Run it manually as:

```bash
venv/bin/python fivech_back_up/thread_backup.py daily
```

Optional flags:
- `--refetch` – also refetches threads already marked as `archived` (≥1000 posts).
- `--search-threshold N` – adjust the post count that triggers successor discovery (default 950).

## One-off and recovery helpers
- `follow-prev` – follows the "前スレ" link from the first post of each thread to backfill older threads.
  ```bash
  venv/bin/python fivech_back_up/thread_backup.py follow-prev https://fate.5ch.net/test/read.cgi/liveuranus/1759563035
  ```
- `import-wiki` – extracts every 5ch URL from one or more wiki pages and adds them to `state.json` so they can be downloaded later.
  ```bash
  venv/bin/python fivech_back_up/thread_backup.py import-wiki https://seesaawiki.jp/nai_ch/d/%b2%e1%b5%ee%a5%ed%a5%b001%2d20 [...]
  ```
  After importing, run `daily --refetch` to download the newly registered threads.

## Manual maintenance
- Update `thread_back_up/latest_thread_url.txt` when the community opens a brand-new thread so the daily job has the right starting point.
- Commit the generated JSON/TXT files to keep history in git (the scheduled push handles this automatically).
- 仮想環境には `requests` と `cloudscraper` が必要です（`pip install cloudscraper`）。
