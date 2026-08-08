"""FastAPI app.

    GET /svg/{login}   the embeddable image (README, blog, portfolio)
    GET /{login}       the interactive page (hover tooltips + timeline)

Both routes run the identical pipeline and the identical renderer. The page
inlines the SVG into the DOM so the browser can attach behaviour to the
data-e / data-t attributes the renderer already emits; the image endpoint
serves the same bytes with an image content type.
"""

from __future__ import annotations

import json
from pathlib import Path
from xml.sax.saxutils import escape

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

import github
import render
from events import build_events, label_for
from grow import grow

BASE = Path(__file__).parent

app = FastAPI(title="GitDNA")
app.mount("/static", StaticFiles(directory=BASE / "static"), name="static")
templates = Jinja2Templates(directory=BASE / "templates")


def _json_for_script(value) -> str:
    """JSON safe to inline in a <script> block.

    json.dumps escapes quotes but not '<', so a release tag containing
    '</script>' would otherwise close the block and inject markup.
    """
    return json.dumps(value).replace("<", "\\u003c").replace("\u2028", "\\u2028")


async def _build(login: str):
    """Fetch -> normalize -> grow. Returns (scene, resolved_login)."""
    raw = await github.fetch_all(login)
    return grow(build_events(raw), raw["login"]), raw["login"]


@app.get("/", response_class=PlainTextResponse)
async def index() -> str:
    return "GitDNA. Try /torvalds or /svg/torvalds\n"


@app.get("/svg/{login}")
async def svg(login: str, theme: str = "light", style: str = "forest") -> Response:
    try:
        scene, resolved = await _build(login)
    except github.UserNotFound:
        return _message_svg(f"no such user: {login}", theme, status=404)
    except github.RateLimited:
        return _message_svg("github rate limit reached, try later", theme, status=503)
    except github.GitHubError as exc:
        return _message_svg(str(exc)[:80], theme, status=502)

    if not scene.nodes:
        return _message_svg(f"{resolved} has no public activity yet", theme, status=200)

    return Response(
        content=render.render(scene, style=style, theme=theme, login=resolved),
        media_type="image/svg+xml",
        headers={"Cache-Control": "public, max-age=1800"},
    )


@app.get("/{login}", response_class=HTMLResponse)
async def profile(
    request: Request, login: str, theme: str = "light", style: str = "forest"
) -> Response:
    try:
        scene, resolved = await _build(login)
    except github.UserNotFound:
        return _message_page(f"no such user: {login}", theme, status=404)
    except github.RateLimited:
        return _message_page("github rate limit reached, try later", theme, status=503)
    except github.GitHubError as exc:
        return _message_page(str(exc)[:120], theme, status=502)

    if not scene.nodes:
        return _message_page(f"{resolved} has no public activity yet", theme, status=200)

    # Only the events actually drawn need labels; sending all of them would
    # roughly quintuple the page for an active account.
    drawn = {node.source_event_id for node in scene.nodes}
    labels = {e.id: label_for(e) for e in scene.events.values() if e.id in drawn}
    style = style if style in render.STYLES else render.DEFAULT_STYLE
    theme = "dark" if theme == "dark" else "light"

    return templates.TemplateResponse(
        request=request,
        name="profile.html",
        context={
            "login": resolved,
            "base": str(request.base_url).rstrip("/"),
            "theme": theme,
            "style": style,
            "styles": list(render.STYLES),
            "stale": False,
            "svg": render.render(scene, style=style, theme=theme, login=""),
            "labels": _json_for_script(labels),
            "dates": _json_for_script(
                {
                    "first": scene.meta.get("first_date", ""),
                    "last": scene.meta.get("last_date", ""),
                }
            ),
            "shown": scene.meta.get("repos_shown", 0),
            "total": scene.meta.get("repos_total", 0),
            "node_count": len(scene.nodes),
        },
    )


def _message_svg(message: str, theme: str, *, status: int) -> Response:
    """Every failure mode still renders a picture -- a README embed that breaks
    shows a broken-image icon, which tells the reader nothing."""
    palette = render.palette.theme_for(theme)
    body = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1200 200" width="1200" '
        f'height="200" font-family="{render.palette.FONT}">'
        f'<rect width="1200" height="200" fill="{palette["bg"]}"/>'
        f'<text x="600" y="105" fill="{palette["text"]}" font-size="16" text-anchor="middle">'
        f"gitdna &#183; {escape(message)}</text></svg>"
    )
    return Response(
        content=body,
        media_type="image/svg+xml",
        status_code=status,
        headers={"Cache-Control": "public, max-age=300"},
    )


def _message_page(message: str, theme: str, *, status: int) -> Response:
    palette = render.palette.theme_for(theme)
    body = (
        '<!doctype html><meta charset="utf-8"><title>GitDNA</title>'
        f'<body style="background:{palette["bg"]};color:{palette["text"]};'
        f'font:14px {render.palette.FONT};display:grid;place-items:center;height:100vh;margin:0">'
        f"<p>gitdna &middot; {escape(message)}</p></body>"
    )
    return HTMLResponse(content=body, status_code=status)
