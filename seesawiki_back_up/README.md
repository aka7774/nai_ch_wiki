# SeesaaWiki backup crawler

This directory contains the Scrapy project that mirrors https://seesaawiki.jp/nai_ch/ . The job `backup` is executed by `gitpush.sh` every day after the 5ch backup.

## Entry point
The helper script `crawl.py` ensures an output directory (`back_up/`) exists and then delegates to Scrapy:

```bash
venv/bin/python seesawiki_back_up/crawl.py backup
```

`backup` is the spider defined under `seesawiki_back_up/spiders/` and writes the latest markup for each wiki page to `back_up/<page>.txt` (UTF-8 encoded).

## Behaviour notes
- Binary attachments and images are not downloaded; only page text is stored.
- The Scrapy settings live in `settings.py`. Middleware and pipeline hooks are under the respective modules should you need to customise the crawl.
- If SeesaaWiki changes its structure, adjust the spiders and rerun the command above.

## Related scripts
Legacy Windows helpers (`*.bat`) live in the project root for manual operation; they remain unchanged by this update.
