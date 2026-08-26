# Combined production image: builds the Angular frontend, then serves it
# same-origin from the FastAPI backend (see backend/app/main.py's
# FRONTEND_DIST static/SPA-fallback route). One container, no CORS, one URL.
#
# Build from the repo root:  docker build -t flatland-dispatcher .
# Run:                       docker run -p 8000:8000 flatland-dispatcher
#
# The `hf-space-*` branches additionally target Hugging Face Docker Spaces:
# the port comes from README.md's `app_port`, and the runtime user is UID 1000
# because that is what Spaces runs the container as.

# Angular CLI 22 requires Node >= 22.22.3 / 24.15.0 / 26.0.0 — node:20 (Render's
# earlier cache) is too old, hence node:24.
FROM node:24-alpine AS frontend-build
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Hugging Face Spaces run the container as UID 1000, so everything owned by
# root is effectively read-only for the app. Own what we copy, and hand the
# user a writable data dir — operator_model.py resolves the carried-over
# profiles to /app/data (it survives a `docker restart`, not a Space rebuild;
# see docs/deploy-hugging-face-space.md on persisting study data).
RUN useradd -m -u 1000 user
COPY --chown=user backend/app ./app
COPY --from=frontend-build --chown=user /app/frontend/dist/frontend/browser ./static
RUN mkdir -p /app/data && chown user /app/data

USER user
ENV HOME=/home/user

EXPOSE 8000
# One worker, always: sessions live in the process (SessionManager._sessions),
# so a second worker would answer requests for sessions it does not have.
# Shell form (not exec-array) so $PORT expands — hosts like Render assign
# their own port at runtime; falls back to 8000 for local `docker run` and for
# Spaces, where README.md's `app_port: 8000` points the proxy at it.
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
