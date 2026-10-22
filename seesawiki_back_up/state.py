"""Small, atomic checkpoint containing metadata only (never page bodies)."""
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

JST = timezone(timedelta(hours=9))


def now():
    return datetime.now(JST).isoformat()


def load(path):
    if not path.exists():
        return {"pages": {}}
    state = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(state, dict) or not isinstance(state.get("pages"), dict):
        raise ValueError("invalid checkpoint")
    for key in ("checked_at", "full_at"):
        if key in state:
            stamp = datetime.fromisoformat(state[key])
            if stamp.tzinfo is None:
                raise ValueError("checkpoint timezone missing")
    for entry in state["pages"].values():
        if not isinstance(entry, dict):
            raise ValueError("invalid checkpoint entry")
        name = entry["file"]
        if not isinstance(name, str):
            raise ValueError("invalid checkpoint filename")
        if Path(name).name != name or not name.endswith(".html"):
            raise ValueError("invalid checkpoint filename")
    return state


def full_due(state, started):
    return state.get("full_at", "")[:7] != started[:7]


def save(path, state):
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(state, ensure_ascii=True, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)
