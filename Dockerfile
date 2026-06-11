# Recipe-card-maker home base (Phase 4α). Multi-stage: build the SvelteKit SPA
# with Node, then assemble a slim Python runtime serving API + SPA via uvicorn.
# Built multi-arch (linux/arm64 for the rpi-k8s cluster, linux/amd64 for local).

FROM node:22-slim AS web
WORKDIR /src/_web
COPY _web/package.json _web/package-lock.json ./
RUN npm ci
COPY _web/ ./
RUN npm run build

FROM python:3.14-slim
WORKDIR /app

COPY requirements.txt requirements-app.txt ./
RUN pip install --no-cache-dir -r requirements-app.txt

# App code + the recipe corpus (seed data for first boot). .dockerignore keeps
# dev/build cruft (venv, node_modules, _web sources, PDFs, git) out.
COPY . .
COPY --from=web /src/_web/build _web/build

# State lives on the mounted volume in production (PVC); the entrypoint creates
# the dirs so a bare `docker run` works too.
ENV RCM_DB_PATH=/data/recipes.db \
    RCM_MEDIA_DIR=/data/media \
    PYTHONUNBUFFERED=1

RUN useradd --uid 1000 --create-home app \
    && mkdir -p /data \
    && chown -R app:app /app /data
USER app

EXPOSE 8000
ENTRYPOINT ["/app/docker/entrypoint.sh"]
