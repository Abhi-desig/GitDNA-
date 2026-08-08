"""Core data types for the GitDNA pipeline.

    GitHub API -> list[GitEvent] -> grow() -> Scene -> render() -> SVG

GitEvent is the normalized, style-agnostic record of something that happened.
Node and Scene are the output of the growth simulation; every renderer consumes
a Scene and nothing else, which is what keeps adding a new visual style cheap.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

EVENT_TYPES = (
    "commit",
    "merge",
    "release",
    "repo_created",
    "fork",
    "star",
    "milestone",
)

NODE_KINDS = ("trunk", "branch", "leaf", "flower", "seed", "spark", "landmark")


@dataclass(frozen=True)
class GitEvent:
    """One thing that happened, stripped of GitHub's JSON shape."""

    id: str
    type: str
    date: date
    repo: str
    weight: int
    meta: dict = field(default_factory=dict)

    def to_json(self) -> dict:
        return {
            "id": self.id,
            "type": self.type,
            "date": self.date.isoformat(),
            "repo": self.repo,
            "weight": self.weight,
            "meta": self.meta,
        }

    @classmethod
    def from_json(cls, data: dict) -> "GitEvent":
        return cls(
            id=data["id"],
            type=data["type"],
            date=date.fromisoformat(data["date"]),
            repo=data["repo"],
            weight=data["weight"],
            meta=data.get("meta") or {},
        )

    @property
    def sort_key(self) -> tuple:
        # Total ordering, so the same input always dumps in the same order.
        return (self.date, self.type, self.repo, self.id)


@dataclass
class Node:
    """One drawn element. `t` is what makes the timeline scrubber free."""

    id: str
    kind: str
    parent_id: str | None
    t: float  # 0..1, when in the user's history this appeared
    x: float
    y: float
    angle: float  # radians
    length: float
    vigor: float  # 0..1, 1.0 = active, low = dormant or wilted
    source_event_id: str


@dataclass
class Scene:
    """Style-agnostic description of the grown organism."""

    seed: int
    width: int
    height: int
    nodes: list[Node] = field(default_factory=list)
    events: dict[str, GitEvent] = field(default_factory=dict)  # id -> event, for tooltips
    meta: dict = field(default_factory=dict)  # e.g. how many repos were shown vs held
