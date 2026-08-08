"""Galaxy style: the same Scene in polar coordinates.

Horizontal position (which repo) becomes the angle around the centre, and
height grown becomes the radius. Every repo turns into an arm radiating out
from a common core, so an account reads as a disc rather than a skyline.

No growth rules are re-implemented here -- this module only re-projects the
nodes grow.py already produced. That is the entire point of the Scene split.
"""

from __future__ import annotations

import math
from collections import defaultdict

from models import Scene
from render.palette import attrs, footer, mix, open_svg, theme_for

OVERRIDES = {
    "light": {"live": (58, 96, 150), "spark": "#d9a13b", "flower": "#d4553d"},
    "dark": {"live": (108, 164, 235), "spark": "#f2c14e", "flower": "#f0764e"},
}

LAYERS = {"spark": 0, "seed": 1, "trunk": 2, "branch": 3, "flower": 4}
CORE_RADIUS = 30


def render(
    scene: Scene, *, theme: str = "light", login: str = "", width: int | None = None
) -> str:
    palette = theme_for(theme, OVERRIDES)
    width_px = width
    width, height = scene.width, scene.height
    out = open_svg(width, height, palette, width_px)

    if not scene.nodes:
        out.append(footer(scene, width, height, palette, login))
        out.append("</svg>")
        return "".join(out)

    centre_x, centre_y = width / 2, (height - 40) / 2
    baseline = height - 70
    max_growth = max(max(baseline - node.y for node in scene.nodes), 1.0)
    # Elliptical, not circular: a circle inscribed in a 1200x630 frame wastes
    # half the canvas. Separate radii let the disc fill the space it is given.
    max_rx = width / 2 - 46
    max_ry = (height - 40) / 2 - 34

    # Each repo gets an equal angular sector. Deriving the angle from raw x
    # instead would crowd every node of a dominant repo into one narrow wedge
    # and leave most of the disc empty.
    repo_of = {
        node.id: (scene.events[node.source_event_id].repo
                  if node.source_event_id in scene.events else "")
        for node in scene.nodes
    }
    repos = sorted(set(repo_of.values()))
    sector = math.tau / max(len(repos), 1)
    index = {repo: i for i, repo in enumerate(repos)}

    spread: dict[str, list[float]] = defaultdict(list)
    for node in scene.nodes:
        spread[repo_of[node.id]].append(node.x)
    mid = {r: (min(v) + max(v)) / 2 for r, v in spread.items()}
    half = {r: max((max(v) - min(v)) / 2, 1.0) for r, v in spread.items()}

    # Project once, then draw; branches need their parent's projected point.
    projected: dict[str, tuple[float, float]] = {}
    for node in scene.nodes:
        repo = repo_of[node.id]
        # Position within the repo's own width becomes a wander inside its wedge.
        offset = (node.x - mid[repo]) / half[repo] * sector * 0.42
        theta = index[repo] * sector + offset
        # sqrt compresses the range: one repo an order of magnitude taller than
        # the rest would otherwise pin everything else against the core.
        reach = math.sqrt((baseline - node.y) / max_growth)
        projected[node.id] = (
            centre_x + math.cos(theta) * (CORE_RADIUS + reach * (max_rx - CORE_RADIUS)),
            centre_y + math.sin(theta) * (CORE_RADIUS + reach * (max_ry - CORE_RADIUS)),
        )

    out.append(
        f'<circle cx="{centre_x:.1f}" cy="{centre_y:.1f}" r="{CORE_RADIUS - 8:.1f}" '
        f'fill="none" stroke="{palette["ground"]}" stroke-width="2"/>'
    )

    for node in sorted(scene.nodes, key=lambda n: LAYERS.get(n.kind, 3)):
        x, y = projected[node.id]
        colour = mix(palette["dead"], palette["live"], node.vigor)
        opacity = 0.35 + 0.65 * node.vigor
        data = attrs(node)

        if node.kind in ("branch", "trunk"):
            parent = projected.get(node.parent_id)
            if parent is None:
                parent = (centre_x, centre_y)
            out.append(
                f'<line {data} x1="{parent[0]:.1f}" y1="{parent[1]:.1f}" '
                f'x2="{x:.1f}" y2="{y:.1f}" stroke="{colour}" '
                f'stroke-width="{3.4 if node.kind == "trunk" else 1.9}" '
                f'stroke-linecap="round" opacity="{opacity:.2f}"/>'
            )
        elif node.kind == "flower":
            out.append(
                f'<circle {data} cx="{x:.1f}" cy="{y:.1f}" r="{node.length:.1f}" '
                f'fill="{palette["flower"]}" opacity="{0.55 + 0.45 * node.vigor:.2f}"/>'
            )
        elif node.kind == "spark":
            out.append(
                f'<circle {data} cx="{x:.1f}" cy="{y:.1f}" r="{node.length:.1f}" '
                f'fill="{palette["spark"]}" opacity="{0.30 + 0.40 * node.vigor:.2f}"/>'
            )
        elif node.kind == "seed":
            out.append(
                f'<circle {data} cx="{x:.1f}" cy="{y:.1f}" r="{node.length:.1f}" '
                f'fill="{palette["seed"]}" opacity="{opacity:.2f}"/>'
            )

    out.append(footer(scene, width, height, palette, login))
    out.append("</svg>")
    return "".join(out)
