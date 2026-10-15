# syntax=docker/dockerfile:1
# The new app's image: the staff app built by Node, served by the Python backend.
# Node exists only in the first stage. Kept in deploy/ (not the repo root) so the
# current site's production build on `main`, which uses buildpacks, is unaffected
# until cutover.
#
#   docker build -f deploy/Dockerfile --build-arg BUILD_ID=$(git rev-parse --short HEAD) .

FROM node:22-slim AS frontend
WORKDIR /src/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
# The translation catalogs are shared with the backend (plan A26).
COPY backend/i18n/ /src/backend/i18n/
ARG BUILD_ID=dev
ENV BUILD_ID=$BUILD_ID
RUN npm run build

FROM python:3.13-slim
COPY --from=ghcr.io/astral-sh/uv:0.13.1 /uv /usr/local/bin/uv
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    PYTHONUNBUFFERED=1
COPY pyproject.toml uv.lock ./
# Only the new app's libraries: no dev tools, none of the current site's.
RUN uv sync --frozen --no-default-groups --no-install-project
COPY backend/ backend/
COPY --from=frontend /src/frontend/dist frontend/dist
ARG BUILD_ID=dev
ENV BUILD_ID=$BUILD_ID \
    FRONTEND_DIST=/app/frontend/dist \
    PATH=/app/.venv/bin:$PATH
RUN useradd --system --uid 10001 app
USER app
EXPOSE 8080
# Cloud Run sets PORT and terminates HTTPS in front; it forwards the client's Host
# (which picks the office) and X-Forwarded-Proto.
CMD ["sh", "-c", "exec uvicorn backend.app:create_app --factory --host 0.0.0.0 --port ${PORT:-8080} --proxy-headers --forwarded-allow-ips='*'"]
