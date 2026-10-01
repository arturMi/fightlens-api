FROM python:3.13-slim

# uv installs the exact package versions from uv.lock
COPY --from=ghcr.io/astral-sh/uv:0.11 /uv /bin/uv

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev
COPY fightlens ./fightlens

ENV PATH="/app/.venv/bin:$PATH"
USER nobody
EXPOSE 8000
CMD ["uvicorn", "fightlens.main:app", "--host", "0.0.0.0", "--port", "8000"]
