"""FastAPI app.

Phase 2 exposes the embeddable image only:

    GET /svg/{login}?theme=dark

The interactive page lands in Phase 3 and will reuse this exact renderer.
"""

from __future__ import annotations

from xml.sax.saxutils import escape

from fastapi import FastAPI
from fastapi.responses import PlainTextResponse, Response

import github
import render
from events import build_events
from grow import grow

app = FastAPI(title="GitDNA")


@app.get("/", response_class=PlainTextResponse)
async def index() -> str:
    return "GitDNA. Try /svg/torvalds\n"


@app.get("/svg/{login}")
async def svg(login: str, theme: str = "light", style: str = "forest") -> Response:
    try:
        raw = await github.fetch_all(login)
    except github.UserNotFound:
        return _message_svg(f"no such user: {login}", theme, status=404)
    except github.RateLimited:
        return _message_svg("github rate limit reached, try later", theme, status=503)
    except github.GitHubError as exc:
        return _message_svg(str(exc)[:80], theme, status=502)

    events = build_events(raw)
    scene = grow(events, raw["login"])
    if not scene.nodes:
        return _message_svg(f"{raw['login']} has no public activity yet", theme, status=200)

    return Response(
        content=render.render(scene, style=style, theme=theme, login=raw["login"]),
        media_type="image/svg+xml",
        headers={"Cache-Control": "public, max-age=1800"},
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
