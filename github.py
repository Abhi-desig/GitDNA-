"""Raw GitHub API access.

Everything here returns unprocessed JSON; turning it into GitEvents is
events.py's job. The one rule enforced here is the request budget:

  - the contribution calendar costs one GraphQL request per YEAR of history
  - releases are fetched for a bounded number of repos, concurrently
  - a user's commit list is never paginated

That keeps even a very active account well inside the 5,000/hour limit.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import httpx

from config import github_token

REST = "https://api.github.com"
GRAPHQL = "https://api.github.com/graphql"

REPO_PAGES = 3  # 100 repos per page
RELEASE_REPOS = 15  # only the most recently pushed repos get a releases call
TIMEOUT = 20.0


class GitHubError(RuntimeError):
    """Anything that went wrong talking to GitHub."""


class UserNotFound(GitHubError):
    pass


class RateLimited(GitHubError):
    pass


class MissingToken(GitHubError):
    pass


CONTRIBUTIONS_QUERY = """
query($login:String!, $from:DateTime!, $to:DateTime!) {
  user(login:$login) {
    contributionsCollection(from:$from, to:$to) {
      contributionCalendar {
        weeks { contributionDays { date contributionCount } }
      }
      commitContributionsByRepository(maxRepositories: 50) {
        repository { name }
        contributions { totalCount }
      }
    }
  }
}
"""


def _headers() -> dict[str, str]:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "gitdna",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    token = github_token()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _check(response: httpx.Response, *, what: str) -> None:
    if response.status_code == 404:
        raise UserNotFound(f"{what} not found")
    remaining = response.headers.get("x-ratelimit-remaining")
    if response.status_code in (403, 429) and remaining == "0":
        raise RateLimited(
            "GitHub rate limit exhausted"
            + ("" if github_token() else " (no GITHUB_TOKEN set: limit is 60/hour)")
        )
    if response.status_code >= 400:
        raise GitHubError(f"{what}: HTTP {response.status_code} {response.text[:200]}")


async def fetch_profile(client: httpx.AsyncClient, login: str) -> dict:
    response = await client.get(f"{REST}/users/{login}")
    _check(response, what=f"user {login}")
    return response.json()


async def fetch_repos(client: httpx.AsyncClient, login: str) -> list[dict]:
    repos: list[dict] = []
    for page in range(1, REPO_PAGES + 1):
        response = await client.get(
            f"{REST}/users/{login}/repos",
            params={"per_page": 100, "page": page, "sort": "pushed"},
        )
        _check(response, what=f"repos for {login}")
        batch = response.json()
        repos.extend(batch)
        if len(batch) < 100:
            break
    return repos


async def fetch_releases(client: httpx.AsyncClient, full_name: str) -> list[dict]:
    response = await client.get(
        f"{REST}/repos/{full_name}/releases", params={"per_page": 20}
    )
    if response.status_code == 404:  # repo has releases disabled; not an error
        return []
    _check(response, what=f"releases for {full_name}")
    return response.json()


async def fetch_releases_many(
    client: httpx.AsyncClient, repos: list[dict]
) -> dict[str, list[dict]]:
    """Releases for a bounded set of repos, fetched concurrently.

    One repo failing must not sink the whole request, so exceptions are
    swallowed per repo and simply yield no releases.
    """
    results = await asyncio.gather(
        *(fetch_releases(client, repo["full_name"]) for repo in repos),
        return_exceptions=True,
    )
    return {
        repo["name"]: result
        for repo, result in zip(repos, results)
        if not isinstance(result, BaseException)
    }


async def fetch_contributions(
    client: httpx.AsyncClient, login: str, created_at: datetime
) -> dict:
    """Daily contribution counts plus real per-repo commit shares, by year.

    GitHub caps each contributionsCollection window at one year, so this loops
    from the account's creation year to now: one request per year, not per day.
    """
    if not github_token():
        raise MissingToken(
            "GITHUB_TOKEN is required for the contribution calendar (GraphQL). "
            "Run with --partial to skip it."
        )

    now = datetime.now(timezone.utc)
    windows = []
    for year in range(created_at.year, now.year + 1):
        start = max(created_at, datetime(year, 1, 1, tzinfo=timezone.utc))
        end = min(now, datetime(year, 12, 31, 23, 59, 59, tzinfo=timezone.utc))
        if start < end:
            windows.append((year, start, end))

    # The years are independent, so fetch them concurrently. Serially this was
    # the dominant cost of a cold render -- one round trip per year of history.
    results = await asyncio.gather(
        *(_fetch_year(client, login, year, start, end) for year, start, end in windows)
    )

    days: dict[str, int] = {}
    by_repo_year: dict[int, dict[str, int]] = {}
    # Merge in year order so the result is identical however the requests raced.
    for (year, _, _), (year_days, shares) in zip(windows, results):
        days.update(year_days)
        if shares:
            by_repo_year[year] = shares

    return {"days": days, "by_repo_year": by_repo_year}


async def _fetch_year(
    client: httpx.AsyncClient, login: str, year: int, start: datetime, end: datetime
) -> tuple[dict[str, int], dict[str, int]]:
    response = await client.post(
        GRAPHQL,
        json={
            "query": CONTRIBUTIONS_QUERY,
            "variables": {
                "login": login,
                "from": start.isoformat(),
                "to": end.isoformat(),
            },
        },
    )
    _check(response, what=f"contributions {year}")
    payload = response.json()
    if payload.get("errors"):
        raise GitHubError(f"GraphQL: {payload['errors'][0].get('message')}")

    user = (payload.get("data") or {}).get("user")
    if user is None:
        raise UserNotFound(f"user {login} not found")
    collection = user["contributionsCollection"]

    days = {
        day["date"]: day["contributionCount"]
        for week in collection["contributionCalendar"]["weeks"]
        for day in week["contributionDays"]
        if day["contributionCount"]
    }
    shares = {
        entry["repository"]["name"]: entry["contributions"]["totalCount"]
        for entry in collection["commitContributionsByRepository"]
    }
    return days, shares


def top_repos(repos: list[dict], limit: int = RELEASE_REPOS) -> list[dict]:
    """The repos worth spending a releases request on: own repos, recently pushed."""
    own = [r for r in repos if not r.get("fork")]
    return sorted(own, key=lambda r: r.get("pushed_at") or "", reverse=True)[:limit]


async def fetch_all(login: str, *, allow_partial: bool = False) -> dict:
    """Everything the pipeline needs, in as few requests as possible.

    allow_partial skips the GraphQL calendar when no token is set, which is
    useful for exercising the REST half offline. The result is not a real
    ecosystem -- it has repos and releases but no commits.
    """
    warnings: list[str] = []

    async with httpx.AsyncClient(timeout=TIMEOUT, headers=_headers()) as client:
        profile = await fetch_profile(client, login)
        created_at = datetime.fromisoformat(profile["created_at"])
        repos = await fetch_repos(client, login)

        top = top_repos(repos)

        # Decide about the token before dispatching, so we never have to
        # re-await a coroutine gather() has already wrapped in a Task.
        if github_token():
            releases, contributions = await asyncio.gather(
                fetch_releases_many(client, top),
                fetch_contributions(client, login, created_at),
            )
        elif allow_partial:
            warnings.append(
                "GITHUB_TOKEN not set: skipped the contribution calendar, "
                "so there are no commit events"
            )
            releases = await fetch_releases_many(client, top)
            contributions = {"days": {}, "by_repo_year": {}}
        else:
            raise MissingToken(
                "GITHUB_TOKEN is required for the contribution calendar (GraphQL). "
                "Run with --partial to skip it."
            )

    return {
        "login": profile["login"],
        "created_at": profile["created_at"],
        "repos": repos,
        "releases": releases,
        "contributions": contributions,
        "warnings": warnings,
    }
