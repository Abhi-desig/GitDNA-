# Must match requires-python in pyproject.toml, or `uv sync --frozen` refuses.
FROM python:3.14-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Dependencies first so code edits don't invalidate the install layer.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY . .

# SQLite cache lives here; mount a volume to keep it across deploys.
ENV GITDNA_DB=/data/gitdna.db
EXPOSE 8000

# Railway, Render and Fly all inject $PORT and expect the app to bind it.
# Hardcoding 8000 makes the container start but never receive traffic.
CMD ["sh", "-c", "uv run uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}"]
