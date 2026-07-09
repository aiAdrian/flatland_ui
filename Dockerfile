# Combined production image: builds the Angular frontend, then serves it
# same-origin from the FastAPI backend (see backend/app/main.py's
# FRONTEND_DIST static/SPA-fallback route). One container, no CORS, one URL.
#
# Build from the repo root:  docker build -t flatland-dispatcher .
# Run:                       docker run -p 8000:8000 flatland-dispatcher

FROM node:20-alpine AS frontend-build
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

COPY backend/app ./app
COPY --from=frontend-build /app/frontend/dist/frontend/browser ./static

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
