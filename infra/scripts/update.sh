#!/usr/bin/env bash
# Ship code only — no infrastructure changes. The fast path for a fix.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TF_DIR="$ROOT/infra/terraform"
AWS_REGION="${AWS_REGION:-ap-south-1}"
TARGET="${1:-all}"   # all | backend | frontend

log() { printf '\033[1m==> %s\033[0m\n' "$*"; }
die() { printf '\033[31merror: %s\033[0m\n' "$*" >&2; exit 1; }

command -v terraform >/dev/null || die "terraform is not installed"
command -v aws >/dev/null       || die "the aws CLI is not installed"

if [[ "$TARGET" == "all" || "$TARGET" == "backend" ]]; then
  log "Testing before shipping"
  ( cd "$ROOT/backend" && .venv/bin/python -m pytest tests/ -q ) || die "backend tests failed — not shipping"

  ECR_REPO="$(terraform -chdir="$TF_DIR" output -raw ecr_repository_url)"
  INSTANCE_ID="$(terraform -chdir="$TF_DIR" output -raw backend_instance_id)"
  TAG="$(git -C "$ROOT" rev-parse --short HEAD)"

  aws ecr get-login-password --region "$AWS_REGION" \
    | docker login --username AWS --password-stdin "${ECR_REPO%%/*}"
  docker build --platform linux/amd64 -f "$ROOT/backend/Dockerfile" \
    -t "$ECR_REPO:$TAG" -t "$ECR_REPO:latest" "$ROOT/backend"
  docker push "$ECR_REPO:$TAG"
  docker push "$ECR_REPO:latest"

  aws ssm send-command --instance-ids "$INSTANCE_ID" \
    --document-name "AWS-RunShellScript" \
    --parameters 'commands=["cd /opt/safespare && docker compose pull && docker compose up -d"]' \
    --region "$AWS_REGION" >/dev/null
  log "Backend shipped as $TAG"
fi

if [[ "$TARGET" == "all" || "$TARGET" == "frontend" ]]; then
  BACKEND_HOST="$(terraform -chdir="$TF_DIR" output -raw backend_public_dns)"
  FRONTEND_BUCKET="$(terraform -chdir="$TF_DIR" output -raw frontend_bucket)"
  DISTRIBUTION_ID="$(terraform -chdir="$TF_DIR" output -raw cloudfront_distribution_id)"

  ( cd "$ROOT/frontend" && npx tsc --noEmit ) || die "type check failed — not shipping"
  ( cd "$ROOT/frontend" && VITE_API_BASE_URL="https://$BACKEND_HOST" npm run build )

  aws s3 sync "$ROOT/frontend/dist" "s3://$FRONTEND_BUCKET" --delete \
    --cache-control "public,max-age=31536000,immutable" --exclude "index.html"
  aws s3 cp "$ROOT/frontend/dist/index.html" "s3://$FRONTEND_BUCKET/index.html" \
    --cache-control "no-cache,no-store,must-revalidate"
  aws cloudfront create-invalidation --distribution-id "$DISTRIBUTION_ID" --paths "/*" >/dev/null
  log "Frontend shipped"
fi
