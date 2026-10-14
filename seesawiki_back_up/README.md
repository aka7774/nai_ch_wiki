# SeesaaWiki backup crawler

This directory contains the Scrapy project that mirrors https://seesaawiki.jp/nai_ch/ . The job `backup` is executed by `gitpush.sh` every day after the 5ch backup.

## Entry point
The helper script `crawl.py` ensures an output directory (`back_up/`) exists and runs Scrapy:

```bash
.venv/bin/python seesawiki_back_up/crawl.py backup
```

`backup` is the spider defined under `seesawiki_back_up/spiders/` and writes the latest markup for each wiki page to `back_up/<page>.txt` (UTF-8 encoded).

The spider uses Scrapy's asynchronous `start()` entry point. The command exits
with status 1 if startup fails or no items pass the saving pipeline in the
current run, even when old backup files exist. A listing or article response
alone does not count as a saved page. HTTP retries use Scrapy's RetryMiddleware;
callbacks do not block the reactor with sleeps.

For a bounded live check, set `WIKI_CHECK_DIR` to an approved temporary location
and run outside the daily collection window:

```bash
.venv/bin/python seesawiki_back_up/crawl.py backup \
  --save-dir "$WIKI_CHECK_DIR/pages" \
  -s CLOSESPIDER_PAGECOUNT=12 -s CLOSESPIDER_ITEMCOUNT=3 \
  -s CLOSESPIDER_TIMEOUT=180 -s CONCURRENT_REQUESTS=1
```

The output goes only to the chosen directory. The normal 3-second download
delay is retained. In-flight requests may finish after a close limit is reached.
Check both the exit status and that text files were created; then remove the
temporary output. Run the offline regression suite with
`PYTHONPATH=. .venv/bin/python -m unittest discover -s tests -q`.

On 2026-10-14 a live check was rejected by robots.txt (`robotstxt/forbidden`):
the site's rules disallowed both listing (`/*/l/`) and editing (`/*/e/`) URLs.
With `ROBOTSTXT_OBEY=True`, that run correctly failed with zero saved pages.
The command's exit status detects this condition; fixing the startup entry
point alone does not establish successful live collection.

## Behaviour notes
- Binary attachments and images are not downloaded; only page text is stored.
- The Scrapy settings live in `settings.py`. Middleware and pipeline hooks are under the respective modules should you need to customise the crawl.
- If SeesaaWiki changes its structure, adjust the spiders and rerun the command above.

## Related scripts
Legacy Windows helpers (`*.bat`) live in the project root for manual operation; they remain unchanged by this update.
