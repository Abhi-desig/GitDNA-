"""Shared theme colours and SVG helpers.

Styles differ in geometry, not in plumbing. Each style may override individual
palette keys (circuit swaps the greens for traces) but they all read from here
so the light/dark contract stays consistent.
"""

from __future__ import annotations

from xml.sax.saxutils import escape

from models import Node

THEMES = {
    "light": {
        "bg": "#fbfaf7",
        "ground": "#e4e0d6",
        "live": (74, 124, 62),
        "dead": (176, 172, 160),
        "flower": "#e0653f",
        "spark": "#e8b23a",
        "seed": "#8a8577",
        "text": "#8c8778",
    },
    "dark": {
        "bg": "#0d1117",
        "ground": "#1f2630",
        "live": (86, 168, 96),
        "dead": (72, 80, 92),
        "flower": "#f0764e",
        "spark": "#f2c14e",
        "seed": "#5a6270",
        "text": "#5c6672",
    },
}

FONT = "ui-monospace,SFMono-Regular,Menlo,monospace"


def theme_for(name: str, overrides: dict | None = None) -> dict:
    palette = dict(THEMES.get(name, THEMES["light"]))
    if overrides:
        palette.update(overrides.get(name, {}))
    return palette


def mix(dead: tuple, live: tuple, amount: float) -> str:
    r, g, b = (round(d + (l - d) * amount) for d, l in zip(dead, live))
    return f"#{r:02x}{g:02x}{b:02x}"


def attrs(node: Node) -> str:
    """The Phase 3 contract: every drawn element is traceable to its event."""
    safe = escape(node.source_event_id, {'"': "&quot;"})
    return f'data-e="{safe}" data-t="{node.t:.4f}"'


MIN_WIDTH, MAX_WIDTH = 240, 2400


def open_svg(width: int, height: int, palette: dict, display_width: int | None = None) -> list[str]:
    """The viewBox always stays at the scene's own coordinates; only the
    presentation size changes, so ?width= never re-runs the simulation."""
    shown = width if display_width is None else max(MIN_WIDTH, min(MAX_WIDTH, display_width))
    return [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
        f'width="{shown}" height="{round(shown * height / width)}" font-family="{FONT}">',
        f'<rect width="{width}" height="{height}" fill="{palette["bg"]}"/>',
    ]


def footer(scene, width: int, height: int, palette: dict, login: str) -> str:
    """READMEs go through Camo, which blocks all interaction, so the image says
    where the interactive version lives. Also states any repo cap outright."""
    if not login:
        return ""
    shown = scene.meta.get("repos_shown")
    total = scene.meta.get("repos_total")
    repos = (
        f"{shown} of {total} repos" if shown and total and total > shown else f"{shown} repos"
    )
    return (
        f'<text x="{width / 2:.0f}" y="{height - 26}" fill="{palette["text"]}" '
        f'font-size="13" text-anchor="middle">{escape(login)} &#183; {repos} &#183; '
        f"explore the timeline &#8594;</text>"
    )
