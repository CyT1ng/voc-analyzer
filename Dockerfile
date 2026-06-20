# --- Stage 1: build the React SPA ---
FROM node:20-slim AS frontend
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm install
COPY frontend/ ./
RUN npm run build          # → /app/frontend/dist

# --- Stage 2: python runtime (uv) ---
FROM python:3.11-slim AS runtime
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
WORKDIR /app

# Install deps first (cached) using the lockfile, then the source.
COPY pyproject.toml uv.lock README.md LICENSE ./
COPY src/ ./src/
COPY data/samples/ ./data/samples/
RUN uv sync --extra web --no-dev --frozen

# The built SPA, served by FastAPI in production.
COPY --from=frontend /app/frontend/dist ./frontend/dist

ENV VOC_WEB_STATIC_DIR=/app/frontend/dist \
    VOC_WEB_HOST=0.0.0.0 \
    VOC_WEB_PORT=8000
EXPOSE 8000

# LLM keys are passed at runtime: `docker run --env-file .env ...` (never baked in).
CMD ["uv", "run", "voc-analyzer-web"]
