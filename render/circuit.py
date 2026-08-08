"""Circuit style: the same Scene drawn as PCB traces.

Identical node positions to the forest; only the path geometry changes. Curves
become right-angle traces, blooms become pads, fireflies become vias.
"""

from __future__ import annotations

from models import Node, Scene
from render.palette import attrs, footer, mix, open_svg, theme_for

OVERRIDES = {
    "light": {
        "live": (24, 122, 116),
        "dead": (183, 186, 180),
        "flower": "#c9821f",
        "spark": "#7aa64f",
        "ground": "#dfe3dd",
    },
    "dark": {
        "live": (44, 190, 170),
        "dead": (60, 74, 78),
        "flower": "#e8a33d",
        "spark": "#8fd14f",
        "ground": "#16241f",
    },
}

LAYERS = {"spark": 0, "seed": 1, "trunk": 2, "branch": 3, "flower": 4}


def render(
    scene: Scene, *, theme: str = "light", login: str = "", width: int | None = None
) -> str:
    palette = theme_for(theme, OVERRIDES)
    width_px = width
    width, height = scene.width, scene.height
    by_id = {node.id: node for node in scene.nodes}
    ground_y = height - 70

    out = open_svg(width, height, palette, width_px)
    out.append(
        f'<line x1="0" y1="{ground_y}" x2="{width}" y2="{ground_y}" '
        f'stroke="{palette["ground"]}" stroke-width="3"/>'
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
            f'stroke-width="6" opacity="{opacity:.2f}"/>'
        )

    if node.kind == "branch":
        parent = by_id.get(node.parent_id)
        if parent is None:
            return ""
        px, py = parent.x, parent.y
        if parent.kind == "trunk":
            py = ground_y - parent.length
        # Right-angle trace: run vertically to the new height, then across.
        return (
            f'<path {data} d="M{px:.1f},{py:.1f} L{px:.1f},{node.y:.1f} '
            f'L{node.x:.1f},{node.y:.1f}" fill="none" stroke="{colour}" '
            f'stroke-width="1.9" stroke-linejoin="miter" opacity="{opacity:.2f}"/>'
        )

    if node.kind == "flower":  # solder pad
        size = node.length * 1.7
        return (
            f'<rect {data} x="{node.x - size / 2:.1f}" y="{node.y - size / 2:.1f}" '
            f'width="{size:.1f}" height="{size:.1f}" fill="{palette["flower"]}" '
            f'opacity="{0.55 + 0.45 * node.vigor:.2f}"/>'
        )

    if node.kind == "spark":  # via
        return (
            f'<rect {data} x="{node.x - node.length:.1f}" y="{node.y - node.length:.1f}" '
            f'width="{node.length * 2:.1f}" height="{node.length * 2:.1f}" '
            f'fill="{palette["spark"]}" opacity="{0.30 + 0.40 * node.vigor:.2f}"/>'
        )

    if node.kind == "seed":
        return (
            f'<rect {data} x="{node.x - node.length:.1f}" y="{node.y - node.length:.1f}" '
            f'width="{node.length * 2:.1f}" height="{node.length * 2:.1f}" '
            f'fill="{palette["seed"]}" opacity="{opacity:.2f}"/>'
        )

    return ""
