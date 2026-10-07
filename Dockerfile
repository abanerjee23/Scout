# syntax=docker/dockerfile:1
FROM node:22-bookworm-slim AS frontend
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./
RUN --mount=type=secret,id=proxy_ca,required=false \
    if [ -f /run/secrets/proxy_ca ]; then export NODE_EXTRA_CA_CERTS=/run/secrets/proxy_ca; fi; npm ci --strict-ssl=true
COPY frontend/ ./
RUN npm run build

FROM ghcr.io/astral-sh/uv:0.11.7 AS uv
FROM python:3.12-slim-bookworm AS runtime
COPY --from=uv /uv /usr/local/bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY backend/ ./backend/
RUN --mount=type=secret,id=proxy_bundle,required=false \
    if [ -f /run/secrets/proxy_bundle ]; then export SSL_CERT_FILE=/run/secrets/proxy_bundle; fi; uv sync --frozen --no-dev
COPY alembic.ini ./
COPY --from=frontend /build/dist ./frontend/dist
ENV UNLOOP_STATIC_DIR=/app/frontend/dist
RUN chmod -R a+rX /app
USER 65532:65532
CMD ["/app/.venv/bin/python", "-m", "unloop.deploy", "web"]
