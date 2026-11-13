"""Shift seed-corpus timestamps so the corpus generator's NOW lands on today.

The corpus generators bake a fixed NOW into every record
(`scripts/generate_corpus.py`: 2026-04-17, `scripts/generate_corpus_v2.py`:
2026-04-18). Phase-2 rulesets filter recall by `time_query` ("last 30 days",
"last 90 days"), which the server measures against its own clock. Seeding
those timestamps unchanged means every phase-2 `/recall` returns nothing once
the corpus is older than the window, and the session-start suites silently
score zero.

`seed_from_snapshot.py` and `seed_corpus.py` therefore move `timestamp`,
`t_valid` and `t_invalid` forward by a whole number of days before posting.
Relative ages are unchanged and embeddings are not touched. The shift is the
largest whole-day count that keeps the anchor at or before the current time,
so no record becomes future-dated (a future `t_valid` is suppressed as
not-yet-valid, and a future `timestamp` falls outside `time_query`).

Dates written inside `content` are not shifted.
"""

from __future__ import annotations

import argparse
import pathlib
from datetime import date, datetime, timedelta, timezone

# Keep in sync with NOW in the generators. Do not import the generators to read
# it: they write their corpus file at import time. test_seed_rebase.py checks
# these against the generator source.
KNOWN_ANCHORS: dict[str, datetime] = {
    "corpus_v1": datetime(2026, 4, 17, 12, 0, 0, tzinfo=timezone.utc),
    "corpus_v2": datetime(2026, 4, 18, 12, 0, 0, tzinfo=timezone.utc),
}

REBASE_FIELDS = ("timestamp", "t_valid", "t_invalid")

ONE_DAY = timedelta(days=1)


def parse_iso(value: str) -> datetime:
    """Parse an ISO-8601 date or datetime. Naive values are treated as UTC."""
    text = value.strip()
    if text.endswith(("Z", "z")):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        parsed = datetime.combine(date.fromisoformat(text), datetime.min.time())
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def shift_iso(value: str, days: int) -> str:
    """Shift an ISO timestamp by whole days, keeping its `Z` / offset style."""
    shifted = (parse_iso(value) + timedelta(days=days)).isoformat()
    if value.strip().endswith(("Z", "z")) and shifted.endswith("+00:00"):
        shifted = shifted[: -len("+00:00")] + "Z"
    return shifted


def shift_entry(entry: dict, days: int) -> dict:
    """Return a shallow copy of `entry` with its time fields shifted.

    Missing or empty fields stay as they are. Other values, including the
    embedding list, are shared with the original rather than copied.
    """
    if days == 0:
        return entry
    shifted = dict(entry)
    for field in REBASE_FIELDS:
        value = shifted.get(field)
        if value:
            shifted[field] = shift_iso(value, days)
    return shifted


def corpus_key(name: str | pathlib.Path) -> str:
    """`corpus_v1.embedded.jsonl` -> `corpus_v1`."""
    return pathlib.Path(name).name.split(".", 1)[0]


def latest_timestamp(entries: list[dict]) -> datetime | None:
    stamps = [parse_iso(e["timestamp"]) for e in entries if e.get("timestamp")]
    return max(stamps) if stamps else None


def resolve_anchor(
    corpus_name: str | pathlib.Path,
    entries: list[dict],
    override: str | None = None,
) -> tuple[datetime | None, str]:
    """Pick the instant that should be moved to "now".

    Order: an explicit override, then the generator NOW for a known corpus,
    then the newest `timestamp` in the data. When the data is newer than the
    known anchor (a snapshot captured after an earlier rebase), the data wins,
    so the newest record still never lands in the future.
    """
    if override:
        return parse_iso(override), "--rebase-anchor"
    known = KNOWN_ANCHORS.get(corpus_key(corpus_name))
    latest = latest_timestamp(entries)
    if known and (latest is None or latest <= known):
        return known, f"generator NOW for {corpus_key(corpus_name)}"
    if latest is not None:
        return latest, "newest timestamp in the data"
    return None, "no timestamps found"


def rebase_days(anchor: datetime, now: datetime | None = None) -> int:
    """Largest whole-day shift that keeps `anchor` at or before `now`."""
    now = now or datetime.now(timezone.utc)
    return (now - anchor) // ONE_DAY


def add_rebase_args(parser: argparse.ArgumentParser) -> None:
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--no-rebase",
        action="store_true",
        help="Seed timestamps exactly as stored instead of shifting them to today.",
    )
    group.add_argument(
        "--rebase-anchor",
        default=None,
        metavar="ISO",
        help=(
            "Instant to move to today (ISO date or datetime; a bare date means "
            "00:00 UTC). Defaults to the generator NOW for corpus_v1/corpus_v2, "
            "else the newest timestamp in the data."
        ),
    )


def plan_rebase(
    args: argparse.Namespace,
    corpus_name: str | pathlib.Path,
    entries: list[dict],
    now: datetime | None = None,
) -> int:
    """Work out the shift for this run and print one line explaining it."""
    if args.no_rebase:
        print("rebase: off (--no-rebase); timestamps seeded as stored")
        return 0
    anchor, source = resolve_anchor(corpus_name, entries, args.rebase_anchor)
    if anchor is None:
        print(f"rebase: skipped ({source})")
        return 0
    days = rebase_days(anchor, now)
    landed = anchor + timedelta(days=days)
    print(
        f"rebase: {days:+d} days ({source}: {anchor.isoformat()} -> "
        f"{landed.isoformat()}); --no-rebase to disable"
    )
    return days
