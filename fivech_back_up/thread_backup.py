"""Utility for backing up 5ch threads for the なんJNVA部 community."""
from __future__ import annotations

import argparse
import datetime as dt
import json
import random
import re
import string
import time
import typing as t
from dataclasses import dataclass, asdict
from html import unescape
from pathlib import Path
from urllib.parse import quote_plus, urlparse

import requests
import cloudscraper


BOARD_DOMAIN_MAP = {
    "liveuranus": "fate",
}

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:143.0) Gecko/20100101 Firefox/143.0"

SEARCH_URL_TEMPLATE = "https://find.5ch.net/search?q={query}"
SEARCH_QUERY = "なんJNVA部"

DATA_DIR_NAME = "thread_back_up"
JSON_DIR_NAME = "json"
TEXT_DIR_NAME = "txt"
STATE_FILE_NAME = "state.json"
LATEST_URL_FILE_NAME = "latest_thread_url.txt"
THREAD_LIST_FILE_NAME = "thread_urls.csv"
DEFAULT_SLEEP_SECONDS = 1.5


class ThreadBackupError(RuntimeError):
    """Raised on unrecoverable errors within the backup workflow."""


@dataclass
class ThreadMeta:
    """Meta data persisted for each backed up thread."""

    dat_id: str
    url: str
    normalized_url: str
    number: t.Optional[int] = None
    title: str = ""
    status: str = "active"  # active | archived
    post_count: int = 0
    last_fetched_at: t.Optional[str] = None
    previous_url: t.Optional[str] = None
    next_url: t.Optional[str] = None
    first_post_at: t.Optional[str] = None
    remark: t.Optional[str] = None

    def to_dict(self) -> dict[str, t.Any]:
        data = asdict(self)
        return {k: v for k, v in data.items() if v is not None}

    @classmethod
    def from_dict(cls, data: dict[str, t.Any]) -> "ThreadMeta":
        return cls(**data)


class FiveChClient:
    """Client for fetching thread data from 5ch new API and search."""

    def __init__(self, session: t.Optional[requests.Session] = None) -> None:
        if session is not None:
            self.session = session
        else:
            self.session = cloudscraper.create_scraper(
                browser={"custom": USER_AGENT},
                delay=10,
            )
        self.session.headers.update({
            "User-Agent": USER_AGENT,
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Accept-Language": "ja-JP,ja;q=0.9,en-US;q=0.8,en;q=0.7",
            "X-Requested-With": "XMLHttpRequest",
        })

    def fetch_thread(self, subdomain: str, board: str, dat_id: str) -> dict[str, t.Any]:
        referer = f"https://itest.5ch.net/read.cgi/{board}/{dat_id}?lr=50"
        last_error: Exception | None = None
        for attempt in range(5):
            rand = self._random_token(10)
            url = (
                "https://itest.5ch.net/public/newapi/client.php?"
                f"subdomain={quote_plus(subdomain)}&"
                f"board={quote_plus(board)}&"
                f"dat={quote_plus(dat_id)}&"
                f"rand={rand}"
            )
            try:
                response = self.session.get(
                    url,
                    timeout=30,
                    headers={
                        "Referer": referer,
                        "X-2ch-UA": "JaneStyle/4.0",
                    },
                )
                response.raise_for_status()
                payload = response.json()
                if not isinstance(payload, dict):
                    raise ThreadBackupError("Unexpected API payload type")
                if "error" in payload:
                    raise ThreadBackupError(str(payload["error"]))
                return payload
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                time.sleep(2 + attempt)
        raise ThreadBackupError(f"Failed to fetch thread {dat_id}: {last_error}")

    def search_threads(self, query: str = SEARCH_QUERY) -> list[dict[str, str]]:
        url = SEARCH_URL_TEMPLATE.format(query=quote_plus(query))
        response = self.session.get(url, timeout=30)
        response.raise_for_status()
        text = response.text
        results: list[dict[str, str]] = []
        link_pattern = r'<a[^>]+href="(https?://[^"]+)"[^>]*>(.*?)</a>'
        for match in re.finditer(link_pattern, text, re.IGNORECASE | re.DOTALL):
            href = unescape(match.group(1))
            label = unescape(re.sub(r"<.*?>", "", match.group(2)))
            if "5ch.net" not in href:
                continue
            results.append({"url": href.split("?")[0], "title": label.strip()})
        return results

    @staticmethod
    def _random_token(length: int) -> str:
        population = string.ascii_letters + string.digits
        return "".join(random.choice(population) for _ in range(length))


def ensure_data_dirs(root: Path) -> tuple[Path, Path, Path]:
    data_dir = root / DATA_DIR_NAME
    json_dir = data_dir / JSON_DIR_NAME
    text_dir = data_dir / TEXT_DIR_NAME
    json_dir.mkdir(parents=True, exist_ok=True)
    text_dir.mkdir(parents=True, exist_ok=True)
    return data_dir, json_dir, text_dir


def load_state(state_path: Path) -> dict[str, t.Any]:
    if not state_path.exists():
        return {"threads": {}}
    with state_path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def save_state(state_path: Path, state: dict[str, t.Any]) -> None:
    tmp_path = state_path.with_suffix(".tmp")
    with tmp_path.open("w", encoding="utf-8") as fh:
        json.dump(state, fh, ensure_ascii=False, indent=2)
    tmp_path.replace(state_path)


def normalize_thread_url(url: str) -> str:
    """Return canonical PC URL for a 5ch thread."""
    subdomain, board, dat_id = parse_thread_url(url)
    return f"https://{subdomain}.5ch.net/test/read.cgi/{board}/{dat_id}"


def parse_thread_url(url: str) -> tuple[str, str, str]:
    cleaned = url.strip()
    cleaned = cleaned.split("#", 1)[0]
    cleaned = cleaned.split("?", 1)[0]
    parsed = urlparse(cleaned if cleaned.endswith("/") else cleaned + "/")

    if not parsed.netloc:
        raise ThreadBackupError(f"Invalid URL: {url}")

    host = parsed.netloc.lower()
    pieces = [p for p in parsed.path.strip("/").split("/") if p]
    if not pieces:
        raise ThreadBackupError(f"Cannot parse thread URL: {url}")

    subdomain = ""
    board = ""
    dat_id = ""

    if host == "itest.5ch.net":
        if len(pieces) >= 5 and pieces[1] == "test" and pieces[2] == "read.cgi":
            # Pattern: /<subdomain>/test/read.cgi/<board>/<dat>
            subdomain = pieces[0]
            board = pieces[3]
            dat_id = pieces[4]
        elif len(pieces) >= 4 and pieces[0] == "test" and pieces[1] == "read.cgi":
            # Pattern: /test/read.cgi/<board>/<dat>
            board = pieces[2]
            dat_id = pieces[3]
            subdomain = BOARD_DOMAIN_MAP.get(board)
        else:
            raise ThreadBackupError(f"Unsupported itest path format: {url}")
        if not subdomain:
            raise ThreadBackupError(f"Missing subdomain information for {url}")
    else:
        subdomain = host.split(".")[0]
        if len(pieces) >= 4 and pieces[0] == "test" and pieces[1] == "read.cgi":
            board = pieces[2]
            dat_id = pieces[3]
        elif len(pieces) >= 3 and pieces[1] == "dat":
            board = pieces[0]
            dat_id = pieces[2].split(".")[0]
        else:
            raise ThreadBackupError(f"Unsupported PC path format: {url}")

    dat_id = dat_id.rstrip("/")
    return subdomain, board, dat_id


def thread_slug(title: str) -> str:
    normalized = re.sub(r"\s+", " ", title).strip()
    slug = re.sub(r"[^0-9A-Za-z\-_. ]", "", normalized)
    slug = slug.replace(" ", "_")
    return slug[:120] if slug else "thread"


def extract_thread_number(title: str) -> t.Optional[int]:
    if not title:
        return None
    star_match = re.search(r"★\s*(\d+)", title)
    if star_match:
        try:
            return int(star_match.group(1))
        except ValueError:
            pass
    digits = re.findall(r"(\d+)", title)
    if not digits:
        return None
    for chunk in reversed(digits):
        try:
            return int(chunk)
        except ValueError:
            continue
    return None


def find_previous_thread_url(text: str) -> t.Optional[str]:
    pattern = r"前スレ[\s\S]*?(https?://\S+)"
    match = re.search(pattern, text, re.IGNORECASE)
    if not match:
        return None
    url = match.group(1).strip()
    url = url.rstrip(')')
    return url


class ThreadBackupManager:
    def __init__(self, root_dir: Path) -> None:
        self.root_dir = root_dir
        self.data_dir, self.json_dir, self.text_dir = ensure_data_dirs(root_dir)
        self.state_path = self.data_dir / STATE_FILE_NAME
        self.latest_url_path = self.data_dir / LATEST_URL_FILE_NAME
        self.list_path = self.data_dir / THREAD_LIST_FILE_NAME
        self.client = FiveChClient()
        self.state = load_state(self.state_path)

    # ------------------------------------------------------------------
    # Public commands
    # ------------------------------------------------------------------
    def run_daily(self, refetch: bool = False, search_threshold: int = 950) -> None:
        if not self.state.get("threads"):
            self._bootstrap_from_latest_file()

        threads = self.state["threads"]
        snapshot_metas = [ThreadMeta.from_dict(meta) for meta in threads.values()]
        latest_primary_number = self._latest_primary_number(snapshot_metas)
        for dat_id, raw_meta in list(threads.items()):
            meta = ThreadMeta.from_dict(raw_meta)
            if meta.status == "archived" and not refetch:
                is_latest_primary = (
                    latest_primary_number is not None
                    and meta.number == latest_primary_number
                    and self._is_primary_thread(meta)
                    and not meta.next_url
                )
                if not is_latest_primary:
                    continue
            self._fetch_and_store(meta)
            threads[dat_id] = meta.to_dict()
            if meta.post_count >= search_threshold:
                new_threads = self._discover_next_threads(meta)
                for new_meta in new_threads:
                    self._fetch_and_store(new_meta)
                    if (
                        meta.number
                        and new_meta.number
                        and new_meta.number == meta.number + 1
                        and not meta.next_url
                    ):
                        meta.next_url = new_meta.normalized_url
                    threads[new_meta.dat_id] = new_meta.to_dict()
                    time.sleep(DEFAULT_SLEEP_SECONDS)
            if meta.post_count >= 1000:
                meta.status = "archived"
            threads[dat_id] = meta.to_dict()
            time.sleep(DEFAULT_SLEEP_SECONDS)

        self._write_latest_url_file()
        self._write_thread_listing()
        save_state(self.state_path, self.state)

    def follow_previous_chain(self, start_url: str, limit: t.Optional[int] = None) -> None:
        current_url = start_url
        visited = 0
        while current_url:
            meta = self._ensure_thread(current_url)
            self._fetch_and_store(meta)
            self.state["threads"][meta.dat_id] = meta.to_dict()
            save_state(self.state_path, self.state)
            previous = meta.previous_url
            visited += 1
            if limit and visited >= limit:
                break
            if not previous:
                break
            current_url = previous
            time.sleep(DEFAULT_SLEEP_SECONDS)

        self._write_latest_url_file()
        self._write_thread_listing()
        save_state(self.state_path, self.state)

    def import_from_wiki(self, wiki_urls: list[str]) -> None:
        for url in wiki_urls:
            candidates = self._extract_thread_urls_from_wiki(url)
            for candidate in candidates:
                meta = self._ensure_thread(candidate)
                if meta.dat_id in self.state["threads"]:
                    continue
                self.state["threads"][meta.dat_id] = meta.to_dict()
        self._write_latest_url_file()
        self._write_thread_listing()
        save_state(self.state_path, self.state)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    def _bootstrap_from_latest_file(self) -> None:
        if not self.latest_url_path.exists():
            raise ThreadBackupError(
                "Latest thread URL file is missing. Create it before running daily backup." )
        with self.latest_url_path.open("r", encoding="utf-8") as fh:
            url = fh.read().strip()
        meta = self._ensure_thread(url)
        self.state["threads"][meta.dat_id] = meta.to_dict()
        save_state(self.state_path, self.state)

    def _ensure_thread(self, url: str) -> ThreadMeta:
        canonical = normalize_thread_url(url)
        subdomain, board, dat_id = parse_thread_url(canonical)
        threads = self.state.setdefault("threads", {})
        existing = threads.get(dat_id)
        if existing:
            meta = ThreadMeta.from_dict(existing)
            meta.url = url
            meta.normalized_url = canonical
            return meta
        number = extract_thread_number(url)
        meta = ThreadMeta(dat_id=dat_id, url=url, normalized_url=canonical, number=number)
        return meta

    def _fetch_and_store(self, meta: ThreadMeta) -> None:
        subdomain, board, dat_id = parse_thread_url(meta.normalized_url)
        payload = self.client.fetch_thread(subdomain, board, dat_id)
        comments = payload.get("comments", [])
        meta.title = payload.get("thread", [None, None, None, None, None, ""])[5]
        meta.post_count = len(comments)
        meta.last_fetched_at = dt.datetime.utcnow().isoformat() + "Z"
        number_from_title = extract_thread_number(meta.title or "")
        if number_from_title:
            meta.number = number_from_title
        if comments:
            first_timestamp = comments[0][3] if len(comments[0]) > 3 else None
            if first_timestamp:
                meta.first_post_at = first_timestamp

        previous = None
        candidate_bodies: list[str] = []
        for comment in comments[:10]:
            if len(comment) > 6 and comment[6]:
                candidate_bodies.append(comment[6])

        for body in candidate_bodies:
            previous = find_previous_thread_url(body or "")
            if previous:
                break

        if previous:
            try:
                meta.previous_url = normalize_thread_url(previous)
            except ThreadBackupError:
                meta.previous_url = previous

        self._store_payload(meta, payload)
        self.state["threads"][meta.dat_id] = meta.to_dict()

    def _store_payload(self, meta: ThreadMeta, payload: dict[str, t.Any]) -> None:
        base = f"{meta.number or meta.dat_id}_{thread_slug(meta.title)}"
        json_path = self.json_dir / f"{base}.json"
        text_path = self.text_dir / f"{base}.txt"

        with json_path.open("w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2)

        with text_path.open("w", encoding="utf-8") as fh:
            fh.write(f"{meta.title}\n\n")
            for comment in payload.get("comments", []):
                post_no = comment[0] if len(comment) > 0 else ""
                user = comment[1] if len(comment) > 1 else ""
                posted_at = comment[3] if len(comment) > 3 else ""
                content = comment[6] if len(comment) > 6 else ""
                fh.write(f"{post_no} {user} {posted_at}\n{content}\n\n")

    def _discover_next_threads(self, meta: ThreadMeta) -> list[ThreadMeta]:
        results = self.client.search_threads()
        threads = self.state.setdefault("threads", {})
        discovered: list[ThreadMeta] = []
        for result in results:
            try:
                canonical = normalize_thread_url(result["url"])
            except ThreadBackupError:
                continue
            _, _, dat_id = parse_thread_url(canonical)
            if dat_id in threads:
                continue
            number = extract_thread_number(result["title"])
            if meta.number and number and number <= meta.number:
                continue
            new_meta = ThreadMeta(
                dat_id=dat_id,
                url=result["url"],
                normalized_url=canonical,
                number=number,
                title=result["title"],
            )
            threads[dat_id] = new_meta.to_dict()
            discovered.append(new_meta)
            if meta.number and number and number == meta.number + 1:
                meta.next_url = canonical
            if not self.latest_url_path.exists() or (number and self._should_update_latest(number)):
                with self.latest_url_path.open("w", encoding="utf-8") as fh:
                    fh.write(canonical + "\n")
        return discovered

    def _is_primary_thread(self, meta: ThreadMeta) -> bool:
        if meta.number is None:
            return False
        if meta.number > 10000:
            return False
        return "なんJNVA部" in (meta.title or "")

    def _latest_primary_number(self, metas: list[ThreadMeta]) -> t.Optional[int]:
        numbers = [m.number for m in metas if self._is_primary_thread(m)]
        if not numbers:
            return None
        return max(numbers)

    def _should_update_latest(self, candidate_number: int) -> bool:
        metas = [ThreadMeta.from_dict(meta) for meta in self.state.get("threads", {}).values()]
        numbers = [m.number for m in metas if m.number]
        if not numbers:
            return True
        return candidate_number >= max(numbers)

    def _write_latest_url_file(self) -> None:
        metas = [ThreadMeta.from_dict(meta) for meta in self.state.get("threads", {}).values()]
        if not metas:
            return

        eligible = [m for m in metas if self._is_primary_thread(m)]
        if eligible:
            latest = max(eligible, key=lambda m: m.number or 0)
        else:
            active = [m for m in metas if m.status != "archived"]
            pool = active if active else metas
            latest = max(pool, key=lambda m: m.number or 0)

        with self.latest_url_path.open("w", encoding="utf-8") as fh:
            fh.write(latest.normalized_url + "\n")

    def _write_thread_listing(self) -> None:
        headings = ["number", "status", "posts", "title", "url", "first_post_at", "remark"]
        lines = [",".join(headings)]
        metas = [ThreadMeta.from_dict(meta) for meta in self.state.get("threads", {}).values()]
        metas.sort(key=lambda m: (m.number or 0, m.dat_id))
        primary_numbers = {
            m.number
            for m in metas
            if m.number and m.number <= 1000 and ("なんJNVA部" in (m.title or "") or "JNVA" in (m.title or ""))
        }
        for meta in metas:
            fields = [
                str(meta.number or ""),
                meta.status,
                str(meta.post_count),
                meta.title.replace(",", " "),
                meta.normalized_url,
                (meta.first_post_at or ""),
                (meta.remark or "").replace(",", " "),
            ]
            lines.append(",".join(fields))

        if primary_numbers:
            max_primary = max(primary_numbers)
            missing_numbers = [
                n for n in range(1, max_primary + 1)
                if n not in primary_numbers
            ]
            for missing in missing_numbers:
                fields = [
                    str(missing),
                    "missing",
                    "0",
                    "",  # title unknown
                    "",
                    "",
                    "欠番",
                ]
                lines.append(",".join(fields))
        with self.list_path.open("w", encoding="utf-8") as fh:
            fh.write("\n".join(lines) + "\n")

    def _extract_thread_urls_from_wiki(self, url: str) -> list[str]:
        response = self.client.session.get(url, timeout=30)
        response.raise_for_status()
        text = response.text
        urls = set()
        pattern = r"""https?://[\w\-/_.]*5ch\.net[^\s<>"']*"""
        for match in re.findall(pattern, text):
            try:
                canonical = normalize_thread_url(match)
            except ThreadBackupError:
                continue
            urls.add(canonical)
        return sorted(urls)


def parse_args(argv: t.Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Backup automation for 5ch threads")
    subparsers = parser.add_subparsers(dest="command")

    daily_parser = subparsers.add_parser("daily", help="Run daily update cycle")
    daily_parser.add_argument("--refetch", action="store_true", help="Force refetch archived threads")
    daily_parser.add_argument(
        "--search-threshold",
        type=int,
        default=950,
        help="Post count threshold for discovering next threads",
    )

    follow_parser = subparsers.add_parser("follow-prev", help="Follow previous thread chain")
    follow_parser.add_argument("start_url", help="Entry point thread URL")
    follow_parser.add_argument("--limit", type=int, default=None, help="Maximum number of threads to follow")

    wiki_parser = subparsers.add_parser("import-wiki", help="Import thread URLs referenced on wiki pages")
    wiki_parser.add_argument("urls", nargs="+", help="Wiki page URLs")

    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="Repository root directory",
    )

    return parser.parse_args(argv)


def main(argv: t.Optional[list[str]] = None) -> None:
    args = parse_args(argv)
    command = args.command or "daily"
    manager = ThreadBackupManager(root_dir=args.root)

    if command == "daily":
        manager.run_daily(refetch=args.refetch, search_threshold=args.search_threshold)
    elif command == "follow-prev":
        manager.follow_previous_chain(args.start_url, limit=args.limit)
    elif command == "import-wiki":
        manager.import_from_wiki(args.urls)
    else:
        raise ThreadBackupError(f"Unknown command: {command}")


if __name__ == "__main__":
    main()
