"""Forest style: repos as plants rooted on a common ground line.

The literal reading of the data -- growth goes up, time goes outward from the
trunk, dormancy drains the colour.
"""

from __future__ import annotations

import math

from models import Node, Scene
from render.palette import attrs, footer, mix, open_svg, theme_for

# Draw order: fireflies behind, blooms in front.
LAYERS = {"spark": 0, "seed": 1, "trunk": 2, "branch": 3, "flower": 4}


def render(
    scene: Scene, *, theme: str = "light", login: str = "", width: int | None = None
) -> str:
    palette = theme_for(theme)
    width_px = width
    width, height = scene.width, scene.height
    by_id = {node.id: node for node in scene.nodes}
    ground_y = height - 70

    out = open_svg(width, height, palette, width_px)
    out.append(
        f'<line x1="0" y1="{ground_y}" x2="{width}" y2="{ground_y}" '
        f'stroke="{palette["ground"]}" stroke-width="2"/>'
    )
    for node in sorted(scene.nodes, key=lambda n: LAYERS.get(n.kind, 3)):
        out.append(_element(node, by_id, palette, ground_y))
    out.append(footer(scene, width, height, palette, login))
    out.append("</svg>")
    return "".join(out)


def _element(node: Node, by_id: dict, palette: dict, ground_y: float) -> str:
    colour = mix(palette["dead"], palette["live"], node.vigor)
    opacity = 0.35 + 0.65 * node.vigor
    data = attrs(node)

    if node.kind == "trunk":
        return (
            f'<line {data} x1="{node.x:.1f}" y1="{ground_y:.1f}" '
            f'x2="{node.x:.1f}" y2="{ground_y - node.length:.1f}" stroke="{colour}" '
            f'stroke-width="7" stroke-linecap="round" opacity="{opacity:.2f}"/>'
        )

    if node.kind == "branch":
        parent = by_id.get(node.parent_id)
        if parent is None:
            return ""
        px, py = parent.x, parent.y
        if parent.kind == "trunk":
            py = ground_y - parent.length
        # A slight perpendicular bow reads as growth rather than as a polyline.
        mx, my = (px + node.x) / 2, (py + node.y) / 2
        bow = node.length * 0.16
        cx = mx + math.cos(node.angle) * bow
        cy = my + math.sin(node.angle) * bow
        return (
            f'<path {data} d="M{px:.1f},{py:.1f} Q{cx:.1f},{cy:.1f} {node.x:.1f},{node.y:.1f}" '
            f'fill="none" stroke="{colour}" stroke-width="2.4" stroke-linecap="round" '
            f'opacity="{opacity:.2f}"/>'
        )

    if node.kind == "flower":
        return (
            f'<circle {data} cx="{node.x:.1f}" cy="{node.y:.1f}" r="{node.length:.1f}" '
            f'fill="{palette["flower"]}" opacity="{0.55 + 0.45 * node.vigor:.2f}"/>'
        )

    if node.kind == "spark":
        return (
            f'<circle {data} cx="{node.x:.1f}" cy="{node.y:.1f}" r="{node.length:.1f}" '
            f'fill="{palette["spark"]}" opacity="{0.30 + 0.40 * node.vigor:.2f}"/>'
        )

    if node.kind == "seed":
        return (
            f'<circle {data} cx="{node.x:.1f}" cy="{node.y:.1f}" r="{node.length:.1f}" '
            f'fill="{palette["seed"]}" opacity="{opacity:.2f}"/>'
        )

    return ""
