# astrolift-sample-function — Knative Serving HTTP function.
#
# Optimized for a fast cold start (scale-to-zero -> first request): a slim
# base, deps installed in their own cached layer, no build toolchain left
# behind, and gunicorn with a small worker count.
#
# Build context is the repo root:
#   docker build -t docker.io/calliopeai/astrolift-sample-function:dev .
FROM python:3.12-slim

# Build metadata, surfaced through /debug at runtime so a running pod traces
# back to its commit + image. Passed by the GitHub Actions build (build.yml).
ARG GIT_SHA=dev
ARG IMAGE_REF=""
ARG BUILT_AT=""
ENV GIT_SHA=${GIT_SHA} \
    IMAGE_REF=${IMAGE_REF} \
    BUILT_AT=${BUILT_AT} \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8080

WORKDIR /app

# Dependency layer first so source edits don't bust the pip cache.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

# Run as a non-root user (Knative-friendly; no root needed at runtime).
RUN useradd --create-home --uid 10001 fnuser
USER fnuser

EXPOSE 8080

# Knative sends the port via $PORT; bind there. Two workers keep the cold-start
# memory/CPU footprint small while still handling the manifest concurrency=10
# (gunicorn's sync workers each serve one request, threads add headroom).
# ``--access-logfile -`` sends request logs to stdout for the platform.
CMD ["sh", "-c", "exec gunicorn --bind 0.0.0.0:${PORT} --workers 2 --threads 8 --timeout 60 --access-logfile - app.main:app"]
