"""Growth simulation: list[GitEvent] -> Scene.

This is the creative core. Events are walked in date order and turned into
nodes; no drawing happens here and no renderer is aware of these rules.

Two things worth knowing about the design:

Commits are bucketed by ISO week per repo before becoming nodes. An active
account produces ~5,000 commit events, and one SVG element each would make a
megabyte of DOM that Phase 3 has to attach hover handlers to. A weekly segment
also simply reads better as growth than a daily one. The events themselves stay
per-day and truthful -- only the drawing aggregates.

Vigor is computed once at the end from how long a repo has been idle *now*,
rather than decayed incrementally as events stream past. Dormancy is a property
of the present state ("this project has been quiet for two years"), and doing it
at the end is O(n) instead of O(n^2).
"""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass
from datetime import date

from models import GitEvent, Node, Scene
from seed import rng_for, seed_for

WIDTH = 1200
HEIGHT = 630
BASELINE = HEIGHT - 70
MARGIN = 110

DORMANT_DAYS = 30
DECAY_PER_MONTH = 0.78
MIN_VIGOR = 0.15
ARCHIVED_VIGOR = 0.2

SEGMENTS_PER_TIP = 13  # a branch grows this far, then bifurcates and retires
MAX_DEPTH = 5
MAX_ANGLE = 0.95  # radians from vertical; keeps growth going upward
ANGLE_RESTORE = 0.80  # pull toward the tip's bias, so drift can't compound
DEPTH_FALLOFF = 0.78  # each branch generation grows shorter segments
BIAS_DAMPING = 0.55  # keeps fan-out from accumulating to the angle clamp
MAX_TIPS = 9
MAX_REPOS = 36  # beyond this the trunks merge into an unreadable bar
TRUNK_HEIGHT = 46
CANVAS_MARGIN = 46


@dataclass
class _Tip:
    """A growing point on one repo's plant."""

    node_id: str
    x: float
    y: float
    angle: float  # radians from vertical, positive = right
    depth: int
    bias: float = 0.0  # direction this tip tends back toward; fans the branches
    budget: int = SEGMENTS_PER_TIP  # segments left before it splits and retires


def _budget(depth: int) -> int:
    return max(4, round(SEGMENTS_PER_TIP * DEPTH_FALLOFF**depth))


def _new_shoot(anchor: tuple[str, float, float], rng) -> _Tip:
    """A fresh stem from the trunk, for when every branch has matured."""
    node_id, x, y = anchor
    return _Tip(node_id, x, y, rng.uniform(-0.25, 0.25), 0, 0.0, _budget(0))


def _week(day: date) -> tuple[int, int]:
    iso = day.isocalendar()
    return (iso.year, iso.week)


def _repo_order(events: list[GitEvent]) -> list[str]:
    """Repos in order of first appearance, so layout is stable."""
    seen: list[str] = []
    for event in events:
        if event.repo not in seen:
            seen.append(event.repo)
    return seen


def _select_repos(events: list[GitEvent]) -> tuple[set[str], int]:
    """Keep the most substantial repos; a 300-repo account is a solid slab.

    Scored by total event weight, which naturally favours repos with real commit
    history over empty ones. The count that got dropped is surfaced in the
    rendered footer rather than silently discarded.
    """
    score: dict[str, int] = defaultdict(int)
    for event in events:
        score[event.repo] += event.weight
    ranked = sorted(score, key=lambda repo: (-score[repo], repo))
    return set(ranked[:MAX_REPOS]), len(ranked)


def grow(events: list[GitEvent], login: str, *, width: int = WIDTH, height: int = HEIGHT) -> Scene:
    scene = Scene(seed=seed_for(login), width=width, height=height)
    if not events:
        return scene

    scene.events = {event.id: event for event in events}
    rng = rng_for(login)

    kept, total_repos = _select_repos(events)
    events = [event for event in events if event.repo in kept]
    if not events:
        return scene
    scene.meta = {"repos_shown": len(kept), "repos_total": total_repos}

    first_day = events[0].date
    last_day = events[-1].date
    span = max((last_day - first_day).days, 1)
    # The page turns a slider position back into a date using these.
    scene.meta["first_date"] = first_day.isoformat()
    scene.meta["last_date"] = last_day.isoformat()

    def t_of(day: date) -> float:
        return min(1.0, max(0.0, (day - first_day).days / span))

    baseline = height - 70
    repos = _repo_order(events)
    positions = _trunk_positions(repos, width, rng)

    tips: dict[str, list[_Tip]] = {}
    anchors: dict[str, tuple[str, float, float]] = {}
    last_active: dict[str, date] = {}
    weeks_grown: dict[str, int] = defaultdict(int)
    archived: set[str] = set()
    node_index: dict[str, list[Node]] = defaultdict(list)
    counter = 0

    def add(node: Node, owner: str) -> Node:
        scene.nodes.append(node)
        node_index[owner].append(node)
        return node

    # Commit events are pre-bucketed so each repo-week produces one segment.
    buckets: dict[tuple[str, tuple[int, int]], list[GitEvent]] = defaultdict(list)
    other: list[GitEvent] = []
    for event in events:
        if event.type == "commit":
            buckets[(event.repo, _week(event.date))].append(event)
        else:
            other.append(event)

    merged: list[GitEvent] = list(other)
    for (repo, _week_key), group in buckets.items():
        total = sum(e.weight for e in group)
        merged.append(
            GitEvent(
                id=group[0].id,
                type="commit",
                date=group[0].date,
                repo=repo,
                weight=total,
                meta={
                    "contributions": total,
                    "days_active": len(group),
                    "attribution": "approximate",
                    "week_of": group[0].date.isoformat(),
                },
            )
        )
    merged.sort(key=lambda e: e.sort_key)
    for event in merged:
        scene.events.setdefault(event.id, event)

    for event in merged:
        repo = event.repo

        if repo not in tips:
            counter += 1
            trunk = Node(
                id=f"n{counter}",
                kind="trunk",
                parent_id=None,
                t=t_of(event.date),
                x=positions.get(repo, width / 2),
                y=baseline,
                angle=0.0,
                length=TRUNK_HEIGHT,
                vigor=1.0,
                source_event_id=event.id,
            )
            add(trunk, repo)
            anchors[repo] = (trunk.id, trunk.x, baseline - TRUNK_HEIGHT)
            tips[repo] = [_new_shoot(anchors[repo], rng)]

        # Every tip can retire, and the bloom/spark helpers index into this list.
        if not tips[repo]:
            tips[repo].append(_new_shoot(anchors[repo], rng))

        if event.meta.get("archived"):
            archived.add(repo)
        last_active[repo] = max(last_active.get(repo, event.date), event.date)

        when = t_of(event.date)
        if event.type == "commit":
            counter = _grow_branch(
                add, tips[repo], anchors[repo], event, when, rng, weeks_grown, repo, counter
            )
        elif event.type == "release":
            counter = _bloom(add, tips[repo], event, when, rng, repo, counter)
        elif event.type == "star":
            counter = _sparks(add, tips[repo], event, when, rng, repo, counter)
        elif event.type == "fork":
            counter = _seed_node(
                add, positions.get(repo, width / 2), baseline, event, when, rng, repo, counter
            )

    _apply_vigor(node_index, last_active, archived, last_day)
    _fit_to_canvas(scene, width, baseline)
    return scene


def _fit_to_canvas(scene: Scene, width: int, baseline: float) -> None:
    """Shrink the organism about the ground line until it fits.

    Growth rates vary hugely between accounts, so rather than tuning segment
    lengths per account, grow freely and scale once at the end. The ground line
    stays put; only height and spread compress.
    """
    if not scene.nodes:
        return

    xs = [node.x for node in scene.nodes]
    min_x, max_x = min(xs), max(xs)
    used_height = baseline - min(node.y for node in scene.nodes)
    used_width = max_x - min_x

    available_height = baseline - CANVAS_MARGIN
    available_width = width - 2 * CANVAS_MARGIN

    # X and Y are scaled independently on purpose. Y is *growth* and a prolific
    # account has to be compressed hard to fit; X is *layout* -- the spacing
    # between repos -- and squeezing it by the same factor would pile every
    # plant into the middle of the canvas.
    scale_y = min(1.0, available_height / used_height) if used_height > 0 else 1.0
    scale_x = min(1.0, available_width / used_width) if used_width > 0 else 1.0
    if scale_x > 0.999 and scale_y > 0.999:
        return

    centre = (min_x + max_x) / 2
    for node in scene.nodes:
        node.x = width / 2 + (node.x - centre) * scale_x
        node.y = baseline - (baseline - node.y) * scale_y
        # Flowers, sparks and seeds are icons, not structure -- shrinking them
        # to a third of a pixel would just delete them from the picture.
        if node.kind in ("trunk", "branch"):
            node.length *= scale_y


def _trunk_positions(repos: list[str], width: int, rng) -> dict[str, float]:
    """Spread trunks across the canvas, with seeded jitter so it isn't a grid."""
    usable = width - 2 * MARGIN
    if len(repos) == 1:
        return {repos[0]: width / 2}
    step = usable / max(len(repos) - 1, 1)
    positions = {}
    for i, repo in enumerate(repos):
        jitter = rng.uniform(-step * 0.18, step * 0.18)
        positions[repo] = MARGIN + i * step + jitter
    return positions


def _grow_branch(add, tips, anchor, event, t, rng, weeks_grown, repo, counter):
    # Every branch has matured, so the plant throws a new stem. This keeps a
    # very long-lived repo growing instead of silently dropping later commits.
    if not tips:
        tips.append(_new_shoot(anchor, rng))

    # Round-robin across every live tip. Always extending the newest tip would
    # abandon older ones and grow a single whip instead of a plant.
    index = weeks_grown[repo] % len(tips)
    tip = tips[index]

    # Segments shorten with depth. Without this a deep tip keeps extending at
    # full speed for the account's whole lifetime and runs off across the canvas.
    length = (5.0 + math.log1p(event.weight) * 4.5) * (DEPTH_FALLOFF**tip.depth)
    # Pull back toward this tip's own bias before jittering. Restoring every tip
    # to vertical would make the branches grow as parallel reeds; restoring each
    # to its own direction fans them into a plant.
    angle = tip.bias + (tip.angle - tip.bias) * ANGLE_RESTORE + rng.uniform(-0.26, 0.26)
    angle = max(-MAX_ANGLE, min(MAX_ANGLE, angle))
    x = tip.x + math.sin(angle) * length
    y = tip.y - math.cos(angle) * length

    counter += 1
    node = Node(
        id=f"n{counter}",
        kind="branch",
        parent_id=tip.node_id,
        t=t,
        x=x,
        y=y,
        angle=angle,
        length=length,
        vigor=1.0,
        source_event_id=event.id,
    )
    add(node, repo)

    tip.node_id, tip.x, tip.y, tip.angle = node.id, x, y, angle
    tip.budget -= 1
    weeks_grown[repo] += 1

    # Spent tips bifurcate and retire. A finite budget per tip is what bounds
    # total reach: without it a shallow tip keeps extending for the account's
    # entire lifetime and runs clean off the canvas.
    if tip.budget <= 0:
        tips.pop(index)
        if tip.depth < MAX_DEPTH:
            for side in (-1, 1):
                if len(tips) >= MAX_TIPS:
                    break
                spread = side * rng.uniform(0.30, 0.55)
                bias = max(-MAX_ANGLE, min(MAX_ANGLE, tip.bias * BIAS_DAMPING + spread))
                tips.append(
                    _Tip(
                        node.id, x, y, angle + spread, tip.depth + 1, bias,
                        _budget(tip.depth + 1),
                    )
                )
    return counter


def _bloom(add, tips, event, t, rng, repo, counter):
    tip = rng.choice(tips)
    counter += 1
    add(
        Node(
            id=f"n{counter}",
            kind="flower",
            parent_id=tip.node_id,
            t=t,
            x=tip.x,
            y=tip.y,
            angle=tip.angle,
            length=6.0,
            vigor=1.0,
            source_event_id=event.id,
        ),
        repo,
    )
    return counter


def _sparks(add, tips, event, t, rng, repo, counter):
    """Stars become fireflies orbiting the plant. Count is logarithmic."""
    count = min(14, max(1, int(math.log1p(event.weight) * 2)))
    tip = tips[0]
    for _ in range(count):
        counter += 1
        radius = rng.uniform(24, 90)
        theta = rng.uniform(0, math.tau)
        add(
            Node(
                id=f"n{counter}",
                kind="spark",
                parent_id=None,
                t=t,
                x=tip.x + math.cos(theta) * radius,
                y=tip.y - abs(math.sin(theta)) * radius * 0.8,
                angle=theta,
                length=rng.uniform(1.2, 2.6),
                vigor=1.0,
                source_event_id=event.id,
            ),
            repo,
        )
    return counter


def _seed_node(add, x, baseline, event, t, rng, repo, counter):
    counter += 1
    add(
        Node(
            id=f"n{counter}",
            kind="seed",
            parent_id=None,
            t=t,
            x=x + rng.uniform(-38, 38),
            y=baseline - rng.uniform(0, 7),
            angle=0.0,
            length=3.2,
            vigor=1.0,
            source_event_id=event.id,
        ),
        repo,
    )
    return counter


def _apply_vigor(node_index, last_active, archived, last_day) -> None:
    """Fade what has gone quiet. Nothing is ever deleted -- it only wilts."""
    for repo, nodes in node_index.items():
        idle_days = (last_day - last_active.get(repo, last_day)).days
        months = max(0, idle_days - DORMANT_DAYS) / 30.0
        vigor = max(MIN_VIGOR, DECAY_PER_MONTH**months)
        if repo in archived:
            vigor = min(vigor, ARCHIVED_VIGOR)
        for node in nodes:
            node.vigor = vigor
