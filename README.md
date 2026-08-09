# GitDNA

Turns a developer's Git history into a procedurally generated living organism
instead of a grid of green squares. Every commit, repo, release, star, fork and
dormant stretch becomes a visual element you can trace back to the event that
made it.

Python 3.13+ · FastAPI · Jinja2 · httpx · SQLite. No TypeScript, no React, no
build step, no graphics library.

## Run it

```bash
uv sync
cp .env.example .env      # then paste a GitHub token into it
uv run uvicorn main:app --reload
```

The token needs **no scopes at all** — reading public repos and public
contribution calendars requires only that the request be authenticated. Without
one, the GraphQL contribution calendar is unavailable and there are no commits.

- `http://localhost:8000/torvalds` — interactive page
- `http://localhost:8000/svg/torvalds` — embeddable image

`/` itself draws nothing: there is no username in it. Set `GITDNA_DEFAULT_USER`
to make it redirect to one garden, which is what you want if you plan to share
the bare host URL.

## Architecture

```
GitHub API  →  list[GitEvent]  →  grow()  →  Scene  →  render.forest(scene)  →  SVG
   fetch          normalize        simulate            render.galaxy(scene)
                                                       render.circuit(scene)
```

The `Scene` describes **what grew, when, and from which event**, with no idea
whether it will be drawn as a tree, a disc or a circuit board. A renderer is a
pure function `Scene → str`. Two properties fall out of this for free:

- **Time travel is a filter, not a re-simulation.** Every node carries
  `t: float` (0–1, when it appeared), so the timeline scrubber hides
  `t > slider` client-side. No refetch, no recompute.
- **One renderer serves both surfaces.** It emits `data-e` and `data-t` on every
  element; the page inlines that SVG so JS can hook the attributes, and the
  image endpoint serves the identical bytes as `image/svg+xml`.

| File | Role |
|---|---|
| `github.py` | Raw API access, and the request budget (one GraphQL call per *year*, concurrently) |
| `events.py` | Raw JSON → `list[GitEvent]`, plus tooltip labels |
| `grow.py` | The growth rules. `list[GitEvent]` → `Scene` |
| `render/*.py` | `Scene` → SVG, one module per style |
| `cache.py` | SQLite, 6h TTL, serves stale when GitHub is down |
| `dump.py` | Dev CLI: `uv run python dump.py torvalds > out.json` |

## Query parameters

| Param | Values | Applies to |
|---|---|---|
| `style` | `forest`, `galaxy`, `circuit` | both |
| `theme` | `light`, `dark` | both |
| `width` | 240–2400 px | `/svg/` only |

`width` changes the presentation size only — the `viewBox` is untouched, so it
never re-runs the simulation.

## Embedding in a GitHub README

```markdown
![GitDNA](https://your-host/svg/yourname?style=forest&theme=dark)
```

Two things to know:

**Hover doesn't work there.** GitHub proxies README images through Camo, which
strips scripts and blocks interaction. The embed is a static picture; tooltips
and the timeline live on the website only, which is why the image carries a
visible "explore the timeline →" line.

**Camo also caches for hours**, so "updates automatically" is true but delayed.
For genuinely fresh output, copy [`examples/gitdna.yml`](examples/gitdna.yml)
into your profile repo — it regenerates the SVG on a schedule and commits it,
so the README points at a file that actually changes.

## Known limitations

- **Commit→repo attribution is approximate.** GitHub's calendar gives daily
  totals across all repos, never per-repo daily counts. GraphQL does give real
  per-repo totals *per year*, so each day's real count is assigned to a repo
  drawn from that year's real shares via the seeded RNG. Daily totals: real.
  Yearly shares: real. Which repo a given day lands on: deterministic fiction,
  flagged as `"attribution": "approximate"` on every commit event.
- **Stars have no date.** GitHub doesn't expose star timestamps cheaply, so star
  events are dated at the repo's last push. All the fireflies therefore appear
  at the end of the timeline rather than accumulating — visible when you scrub.
- **Merge and milestone events emit nothing.** Both need per-commit or per-repo
  calls that break the request budget. The types exist in the model; the sources
  don't.
- **Repos are capped at 36** (by total event weight). Beyond that the trunks
  merge into an unreadable bar. The rendered footer says "36 of 434 repos"
  rather than pretending it drew everything.
- **`og:image` points at an SVG**, which most social platforms won't render.
  Real previews need a raster step (`cairosvg` or similar) that would pull in a
  native dependency.

## Deploy

```bash
docker build -t gitdna . && docker run -p 8000:8000 --env-file .env gitdna
```

Mount a volume and set `GITDNA_DB=/data/gitdna.db` to keep the cache across
restarts. Any host that runs a container works; skip Vercel, whose Python
runtime is fiddly and buys nothing here.

| Variable | Effect |
|---|---|
| `GITHUB_TOKEN` | Required for commits. Without it there is no contribution calendar |
| `GITDNA_DEFAULT_USER` | Optional. Redirects `/` to that login instead of the placeholder line |
| `GITDNA_DB` | Optional. Cache location; point it at a mounted volume to survive restarts |
