# Specification

This repository backs up SeesaaWiki pages and related 5ch threads and publishes
archive updates through its configured Git remote.

## Required user-visible behavior (must)

1. The wiki backup must save retrieved editable page text under `back_up/`,
   using page titles as filenames and replacing `/` with `_`.
2. The thread backup must retain fetched thread responses as JSON and readable
   TXT exports under `thread_back_up/`, with persistent metadata for later runs.
3. The daily thread command must discover current matching threads, update the
   current-thread URL, and backfill missed threads through previous-thread links.
4. Threads with at least 1000 posts must normally stop being fetched again;
   `daily --refetch` must allow fetching archived threads again.
5. Users must be able to follow a previous-thread chain with `follow-prev` and
   register thread URLs from wiki pages with `import-wiki`.
6. Thread processing must produce a CSV index of known thread numbers and URLs,
   including missing-number entries and provenance for manually imported data.
7. The daily wrapper must run local regression tests before collection and stop
   on a dependency, regression-test, or wiki-crawler command failure. A thread
   backup failure must allow the wiki backup to continue but report exit status 2
   if the remaining workflow succeeds.
8. After collection, the daily wrapper must commit and push changed archive
   data to its configured Git remote, and skip creating an archive commit when
   the tracked archive data has not changed.

## Scope and limits

Source-site availability and markup determine what can be retrieved. Scheduler
configuration, credentials, and Git push permission are supplied by the operator.
A successful crawler process alone does not prove that every source page was
retrieved. See README for rebuild instructions and verification coverage.
