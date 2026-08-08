"""Phase 1 dev CLI -- read the data with your own eyes before trusting it.

    uv run python dump.py torvalds > out.json
    uv run python dump.py torvalds --partial     # no token: repos + releases only

Output is deterministic: the same account must dump byte-identical JSON twice.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections import Counter

import github
from events import build_events
from seed import seed_for


def summarize(login: str, events: list) -> dict:
    counts = Counter(event.type for event in events)
    repos = sorted({event.repo for event in events})
    return {
        "login": login,
        "seed": seed_for(login),
        "event_count": len(events),
        "by_type": dict(sorted(counts.items())),
        "repo_count": len(repos),
        "first_event": events[0].date.isoformat() if events else None,
        "last_event": events[-1].date.isoformat() if events else None,
    }


async def main() -> int:
    parser = argparse.ArgumentParser(description="Dump a user's normalized GitDNA events")
    parser.add_argument("login")
    parser.add_argument(
        "--partial",
        action="store_true",
        help="skip the GraphQL contribution calendar when no GITHUB_TOKEN is set",
    )
    args = parser.parse_args()

    try:
        raw = await github.fetch_all(args.login, allow_partial=args.partial)
    except github.GitHubError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    for warning in raw.get("warnings") or []:
        print(f"warning: {warning}", file=sys.stderr)

    events = build_events(raw)
    payload = {
        "summary": summarize(raw["login"], events),
        "events": [event.to_json() for event in events],
    }
    print(json.dumps(payload, indent=2, sort_keys=True))

    summary = payload["summary"]
    print(
        f"{summary['event_count']} events, {summary['repo_count']} repos, "
        f"{summary['first_event']} -> {summary['last_event']}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
