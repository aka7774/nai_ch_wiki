# SeesaaWiki backup crawler

Run `.venv/bin/python seesawiki_back_up/crawl.py backup` from the repository.
The default `--mode auto` reads `site.rdf` for recently updated articles.
Only changed timestamps, new URLs and missing local files cause article requests.
Daily runs do not follow article links. An unchanged, valid feed succeeds with
zero saved pages. `--mode full` explicitly requests a full traversal.

## Full checks and missing pages

The first run establishes a baseline. Thereafter, the first successful run in
each calendar month (JST) traverses the top page, RSS entries, previously known
URLs and legacy filenames, following article links. It checks for unlinked known
pages and locally missing files. HTTP 404s are counted and listed as URL metadata
in the checkpoint; archived files are retained. Missing bodies, HTTP/network
failures, pipeline errors, malformed/empty RSS and interrupted crawls fail the
run and retain the previous checkpoint so pending changes are retried.

The official RSS has only five items (verified 2026-10-22 JST). If all items are
newer than the previous successful check, coverage may have been lost: a warning
and an exceptional full traversal recover discoverable pages immediately.
This can happen frequently on a busy wiki. A full traversal cannot discover an
unknown page that has no incoming links and has already left the feed. It also
cannot guarantee recovery of every intermediate revision. Edits that suppress
the update timestamp are refreshed by the monthly traversal.

`back_up_html/.crawl-state.json` holds timestamps, URL-to-filename mappings and
missing-URL metadata, never bodies. It is atomically replaced only after a
complete successful crawl, and committed with the HTML by `gitpush.sh`. Keep it
with the archive when restoring. A missing checkpoint causes a new full baseline;
a malformed checkpoint fails rather than being silently discarded. Local
`.crawl.lock` excludes simultaneous crawlers using the same output directory;
`.backup.lock` excludes overlapping daily wrapper runs.

## Collection policy

[robots.txt](https://seesaawiki.jp/robots.txt) disallows listing, history, editing
and API URLs. The crawler always obeys it and uses only the top page, `site.rdf`
and permitted article links. No usable official reader export was found in the
review; no authenticated/export API or headless-browser workaround is used.
The [official RSS feed](https://seesaawiki.jp/nai_ch/site.rdf) supplies article
links and timezone-aware Dublin Core dates. No page bodies were needed to inspect
its structure. Requests are serialized per domain with a minimum four-second
delay and AutoThrottle. Retries use Scrapy's bounded retry middleware.

Page bodies are UTF-8 HTML from `div.user-area`, saved under their titles with
slashes replaced by underscores. `back_up/` retains old wiki source and is not
modified. Images and attachments are not fetched. Existing sanitized filenames
can be ambiguous (slash versus underscore); a full traversal tries both legacy
URL forms and preserves old files.

## Logs and verification

Logs contain counts and status rather than item bodies. The custom log formatter
omits scraped and failed item payloads. The CLI caps DEBUG at INFO, forces robots
compliance, and disables the telnet console. Do not print archived bodies for
diagnostics. `--save-dir` chooses a separate output/checkpoint directory.

Run offline tests with `PYTHONPATH=. .venv/bin/python -m unittest discover -s tests -q`
using an approved `TMPDIR`. Tests cover changed/unchanged feeds, coverage gaps,
missing local files, 404s, malformed feeds, month boundaries, failure checkpoint
retention, logging and actual reactor/pipeline execution with synthetic HTML.
`.venv/bin/python seesawiki_back_up/crawl.py --help` checks the direct entry point.

For a bounded full live check use a temporary `--save-dir`, `--mode full` and
`-s CLOSESPIDER_PAGECOUNT=12 -s CLOSESPIDER_TIMEOUT=180`. A limited crawl deliberately
returns nonzero and does not advance its checkpoint. Never treat that result as a
complete backup. Remove only the temporary test output afterward.

On 2026-10-22 JST, 31 offline tests, crawler discovery, direct-script loading and
shell syntax checks passed. An isolated incremental live check saved five RSS
pages; repeating it saved zero pages and succeeded. Archived bodies were not
printed or inspected. Monthly traversal and failures were exercised with
synthetic responses, not a new full live crawl.
