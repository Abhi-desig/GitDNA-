"""Normalize raw GitHub JSON into one chronological list[GitEvent].

Attribution note, because it matters and is easy to forget later:

GitHub's contribution calendar reports DAILY TOTALS across all repositories, not
per-repo daily counts. GraphQL does give real per-repo commit totals per year,
so each day's real commit count is assigned to a repo drawn from that year's
real shares using the user's seeded RNG. The daily totals are real and the
yearly per-repo shares are real; which specific repo a given day lands on is a
deterministic approximation. Nothing else in the pipeline approximates.

Merge and milestone events are not populated yet -- both need per-commit or
per-repo calls that would blow the request budget. They are Phase 4 work.
"""

from __future__ import annotations

from datetime import date, datetime

from models import GitEvent
from seed import rng_for


def _as_date(value: str | None) -> date | None:
    if not value:
        return None
    return datetime.fromisoformat(value).date()


def _repo_events(repos: list[dict]) -> list[GitEvent]:
    """Creation of each repo, plus one star event per starred repo.

    Stars have no timestamp without paginating the stargazer list, so they are
    dated at the repo's last push -- the cheapest honest proxy we have.
    """
    events: list[GitEvent] = []
    for repo in repos:
        name = repo["name"]
        created = _as_date(repo.get("created_at"))
        if created:
            is_fork = bool(repo.get("fork"))
            events.append(
                GitEvent(
                    id=f"{'fork' if is_fork else 'repo_created'}:{name}",
                    type="fork" if is_fork else "repo_created",
                    date=created,
                    repo=name,
                    weight=1,
                    meta={
                        "language": repo.get("language") or "",
                        "description": (repo.get("description") or "")[:140],
                        "archived": bool(repo.get("archived")),
                    },
                )
            )

        stars = repo.get("stargazers_count") or 0
        pushed = _as_date(repo.get("pushed_at"))
        if stars > 0 and pushed:
            events.append(
                GitEvent(
                    id=f"star:{name}",
                    type="star",
                    date=pushed,
                    repo=name,
                    weight=stars,
                    meta={"stars": stars, "dated_by": "pushed_at"},
                )
            )
    return events


def _release_events(releases: dict[str, list[dict]]) -> list[GitEvent]:
    events: list[GitEvent] = []
    for repo_name, entries in releases.items():
        for release in entries:
            published = _as_date(release.get("published_at"))
            if not published or release.get("draft"):
                continue
            tag = release.get("tag_name") or "release"
            events.append(
                GitEvent(
                    id=f"release:{repo_name}:{tag}",
                    type="release",
                    date=published,
                    repo=repo_name,
                    weight=1,
                    meta={
                        "tag": tag,
                        "name": (release.get("name") or "")[:120],
                        "prerelease": bool(release.get("prerelease")),
                    },
                )
            )
    return events


def _commit_events(contributions: dict, login: str) -> list[GitEvent]:
    days: dict[str, int] = contributions.get("days") or {}
    by_repo_year: dict = contributions.get("by_repo_year") or {}
    rng = rng_for(login)
    events: list[GitEvent] = []

    # Sorted iteration keeps the RNG draw sequence stable across runs.
    for iso in sorted(days):
        count = days[iso]
        if count <= 0:
            continue
        day = date.fromisoformat(iso)
        shares = by_repo_year.get(day.year) or by_repo_year.get(str(day.year)) or {}
        repo = _pick_repo(shares, rng)
        events.append(
            GitEvent(
                id=f"commit:{repo}:{iso}",
                type="commit",
                date=day,
                repo=repo,
                weight=count,
                meta={"contributions": count, "attribution": "approximate"},
            )
        )
    return events


def _pick_repo(shares: dict[str, int], rng) -> str:
    """Weighted draw from a year's real per-repo commit shares."""
    names = sorted(shares)
    weights = [shares[name] for name in names]
    if not names or sum(weights) <= 0:
        return "(unattributed)"
    return rng.choices(names, weights=weights, k=1)[0]


_MONTHS = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()


def label_for(event: GitEvent) -> str:
    """Human-readable tooltip text. Precomputed here so the page ships strings
    rather than a second copy of the event model in JavaScript."""
    when = f"{event.date.day} {_MONTHS[event.date.month - 1]} {event.date.year}"

    if event.type == "commit":
        days = event.meta.get("days_active", 1)
        plural = "s" if event.weight != 1 else ""
        span = f" over {days} days" if days > 1 else ""
        return f"{event.weight} commit{plural}{span} · week of {when} · {event.repo}"
    if event.type == "release":
        return f"Released {event.meta.get('tag', '')} · {when} · {event.repo}"
    if event.type == "repo_created":
        language = event.meta.get("language")
        return f"Created {event.repo}{f' ({language})' if language else ''} · {when}"
    if event.type == "fork":
        return f"Forked {event.repo} · {when}"
    if event.type == "star":
        return f"{event.weight:,} stars · {event.repo}"
    return f"{event.type} · {event.repo} · {when}"


def build_events(raw: dict) -> list[GitEvent]:
    events = [
        *_repo_events(raw.get("repos") or []),
        *_release_events(raw.get("releases") or {}),
        *_commit_events(raw.get("contributions") or {}, raw["login"]),
    ]
    return sorted(events, key=lambda event: event.sort_key)
