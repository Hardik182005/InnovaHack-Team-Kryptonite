# syntax=docker/dockerfile:1
######################################################################
# SafeSpare AI — backend image
#
# Multi-stage so the runtime layer carries no compiler toolchain: build
# wheels in `builder`, copy only the installed site-packages forward.
# Result is a smaller image with a smaller attack surface.
#
# NO SECRET IS EVER BAKED INTO A LAYER. There is no ARG for an API key, no
# COPY of a .env file (.dockerignore excludes them), and no `pip config` with
# credentials. Every secret is read from the environment at *runtime*, which
# on AWS means SSM Parameter Store SecureString -> /opt/safespare/app.env ->
# docker compose env_file (see infra/terraform/compute.tf). Layers are world
# readable to anyone who can pull the image; environment variables at runtime
# are not (§22, §33).
#
# The app is designed to start with every provider key blank, so this image
# is fully functional with no secrets configured at all (deterministic mode).
#
# Build (from the repo root; the EC2 host is x86_64 so force the platform if
# you are on an Apple Silicon Mac):
#   docker build --platform linux/amd64 -f backend/Dockerfile -t safespare-api backend/
######################################################################

######################################################################
# Stage 1 — builder
######################################################################
FROM python:3.11-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# build-essential is needed for any dependency without a manylinux wheel;
# it stays in this stage and never reaches the runtime image.
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      build-essential \
      curl \
 && rm -rf /var/lib/apt/lists/*

# A venv rather than --user or system site-packages: it copies forward as one
# self-contained directory, so the runtime stage needs no pip at all.
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:${PATH}"

WORKDIR /build

# Copied alone so the (slow) dependency layer is cached independently of
# application source — editing a .py file must not trigger a full reinstall.
#
# NOTE: backend/requirements.txt is owned by the backend agent and did NOT
# exist when this Dockerfile was written. The build fails fast and clearly if
# it is still missing rather than silently producing an image with no deps.
COPY requirements.txt ./
RUN pip install --upgrade pip setuptools wheel \
 && pip install -r requirements.txt

######################################################################
# Stage 2 — runtime
######################################################################
FROM python:3.11-slim AS runtime

# PYTHONPATH so `app.main:app` resolves; HF_HOME/TRANSFORMERS_CACHE point at a
# writable directory the non-root user owns, otherwise sentence-transformers
# tries to write to /root and dies at first embed.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:${PATH}" \
    PYTHONPATH=/app \
    HF_HOME=/home/app/.cache/huggingface \
    TRANSFORMERS_CACHE=/home/app/.cache/huggingface \
    SENTENCE_TRANSFORMERS_HOME=/home/app/.cache/huggingface \
    PORT=8000

# curl for the HEALTHCHECK below; libgomp1 is a runtime dependency of the
# ONNX/torch stack that sentence-transformers pulls in.
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      curl \
      libgomp1 \
 && rm -rf /var/lib/apt/lists/* \
 && useradd --create-home --uid 10001 --shell /usr/sbin/nologin app

COPY --from=builder /opt/venv /opt/venv

WORKDIR /app

# --chown at COPY time rather than a later `chown -R`, which would duplicate
# every file into a second layer and roughly double the image size.
COPY --chown=app:app . /app

# Cache directory for the MiniLM weights, owned by the runtime user.
RUN mkdir -p /home/app/.cache/huggingface \
 && chown -R app:app /home/app/.cache

# Non-root from here on (§22). uid 10001 is well outside the host's normal
# uid range, so a container escape does not land on a real host account.
USER app

EXPOSE 8000

# Container-level liveness, independent of the CloudWatch/Route 53 checks in
# infra/terraform/monitoring.tf. start-period is generous because the first
# request may load the MiniLM model into memory.
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
  CMD curl -fsS "http://127.0.0.1:${PORT}/health" || exit 1

# One worker on purpose: the instance is a 2 vCPU / 2 GiB t3.small and each
# uvicorn worker would load its own copy of the embedding model. Scale with a
# bigger instance, not with workers.
#
# Entrypoint form (not shell form) so uvicorn is PID 1 and receives SIGTERM
# directly — `docker stop` then shuts down gracefully instead of timing out.
ENTRYPOINT ["uvicorn"]
CMD ["app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--proxy-headers", "--forwarded-allow-ips", "*"]
