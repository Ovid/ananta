# Shesha Document Explorer
# Build:  docker compose build
# Run:    docker compose up
# See:    http://localhost:8003

# --- Stage 1: Build frontend ---
FROM node:20-slim AS frontend

WORKDIR /build

# Copy shared UI library first (local dependency)
COPY src/shesha/experimental/shared/frontend/ /shared-ui/

# Copy document explorer frontend (lockfile excluded — npm install regenerates it
# because the local file: dependency path is rewritten for Docker context)
COPY src/shesha/experimental/document_explorer/frontend/package.json ./

# Rewrite the local dependency path for the Docker build context
RUN sed -i 's|file:../../shared/frontend|file:/shared-ui|' package.json

RUN npm install --install-links
COPY src/shesha/experimental/document_explorer/frontend/ ./
RUN npm run build

# --- Stage 2: Runtime ---
FROM python:3.12-slim

WORKDIR /app
COPY . .

# Copy built frontend into the source tree
COPY --from=frontend /build/dist src/shesha/experimental/document_explorer/frontend/dist

# .git is excluded by .dockerignore, so provide version via env var
ENV SETUPTOOLS_SCM_PRETEND_VERSION=0.0.0
RUN pip install --no-cache-dir -e ".[document-explorer]"

EXPOSE 8003

ENTRYPOINT ["shesha-document-explorer", "--no-browser", "--data-dir", "/data"]
