# syntax=docker/dockerfile:1.7
# Shelfpass container image: gunicorn + whitenoise, dataset bundled.
ARG PYTHON_VERSION=3.13

FROM ghcr.io/astral-sh/uv:0.13 AS uv

# ----------------------------------------------------------------- build ---
FROM python:${PYTHON_VERSION}-slim AS build
COPY --from=uv /uv /bin/uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/app/.venv
WORKDIR /src

# Dependencies first so they cache independently of the source.
COPY pyproject.toml uv.lock README.md LICENSE ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-install-project

COPY shelfpass ./shelfpass
COPY manage.py ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-editable

RUN SHELFPASS_ALLOW_INSECURE_KEY=1 SHELFPASS_STATIC_ROOT=/app/staticfiles \
    /app/.venv/bin/python manage.py collectstatic --noinput --verbosity 0

# --------------------------------------------------------------- runtime ---
FROM python:${PYTHON_VERSION}-slim AS runtime

ARG VERSION=dev
ARG BUILD_NUMBER=dev
ARG GIT_SHA=unknown
ARG BUILD_DATE=unknown

LABEL org.opencontainers.image.title="Shelfpass" \
      org.opencontainers.image.description="Request tracker for books-to-prisoners groups, with a shared dataset of prison mail rules." \
      org.opencontainers.image.source="https://github.com/lobojoel2003/Shelfpass" \
      org.opencontainers.image.licenses="AGPL-3.0-or-later" \
      org.opencontainers.image.version="${VERSION}" \
      org.opencontainers.image.revision="${GIT_SHA}" \
      org.opencontainers.image.created="${BUILD_DATE}"

RUN groupadd --system --gid 10001 shelfpass \
 && useradd --system --uid 10001 --gid shelfpass --home-dir /app --shell /usr/sbin/nologin shelfpass

WORKDIR /app
COPY --from=build /app/.venv /app/.venv
COPY --from=build /app/staticfiles /app/staticfiles
COPY manage.py ./
COPY dataset ./dataset
COPY docker/entrypoint.sh /usr/local/bin/shelfpass-entrypoint
RUN chmod 0755 /usr/local/bin/shelfpass-entrypoint \
 && printf '{"version": "%s", "build_number": "%s", "commit": "%s", "build_date": "%s"}\n' \
      "${VERSION}" "${BUILD_NUMBER}" "${GIT_SHA}" "${BUILD_DATE}" > /app/BUILD_INFO.json

ENV PATH="/app/.venv/bin:${PATH}" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    SHELFPASS_STATIC_ROOT=/app/staticfiles \
    SHELFPASS_DATASET_DIR=/app/dataset \
    SHELFPASS_BUILD_INFO=/app/BUILD_INFO.json \
    SHELFPASS_BEHIND_PROXY=1 \
    PORT=8000

USER shelfpass
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD ["python", "-c", "import os, sys, urllib.request; sys.exit(0 if urllib.request.urlopen(f\"http://127.0.0.1:{os.environ.get('PORT', '8000')}/healthz\", timeout=4).status == 200 else 1)"]

ENTRYPOINT ["shelfpass-entrypoint"]
CMD ["web"]
