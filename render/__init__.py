"""Renderers: Scene -> SVG string.

Every renderer is a pure function with the same signature, so adding a style
means adding a module here plus one line in STYLES -- nothing upstream changes.
"""

from __future__ import annotations

from render import circuit, forest, galaxy, palette

STYLES = {
    "forest": forest.render,
    "galaxy": galaxy.render,
    "circuit": circuit.render,
}

DEFAULT_STYLE = "forest"


def render(
    scene,
    *,
    style: str = DEFAULT_STYLE,
    theme: str = "light",
    login: str = "",
    width: int | None = None,
) -> str:
    renderer = STYLES.get(style, STYLES[DEFAULT_STYLE])
    return renderer(scene, theme=theme, login=login, width=width)
