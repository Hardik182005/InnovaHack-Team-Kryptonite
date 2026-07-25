#!/usr/bin/env bash
# Full deploy: infrastructure, backend image, frontend bundle.
#
# Requires terraform and the aws CLI. Neither is installed on the development
# machine this was written on, so this script has NOT been executed end to end —
# see AWS_DEPLOYMENT.md. Every step is idempotent and safe to re-run.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TF_DIR="$ROOT/infra/terraform"
ENVIRONMENT="${ENVIRONMENT:-dev}"
AWS_REGION="${AWS_REGION:-ap-south-1}"

log() { printf '\033[1m==> %s\033[0m\n' "$*"; }
die() { printf '\033[31merror: %s\033[0m\n' "$*" >&2; exit 1; }

command -v terraform >/dev/null || die "terraform is not installed"
command -v aws >/dev/null       || die "the aws CLI is not installed"
command -v docker >/dev/null    || die "docker is not installed"
aws sts get-caller-identity >/dev/null 2>&1 || die "no valid AWS credentials (try: aws sso login)"

log "Validating Terraform"
terraform -chdir="$TF_DIR" init -input=false
terraform -chdir="$TF_DIR" fmt -check
terraform -chdir="$TF_DIR" validate

log "Planning"
terraform -chdir="$TF_DIR" plan -input=false -var="environment=$ENVIRONMENT" -out=tfplan
read -r -p "Apply this plan? [y/N] " reply
[[ "$reply" == "y" || "$reply" == "Y" ]] || die "aborted by user"

log "Applying"
terraform -chdir="$TF_DIR" apply -input=false tfplan

BACKEND_HOST="$(terraform -chdir="$TF_DIR" output -raw backend_public_dns)"
FRONTEND_BUCKET="$(terraform -chdir="$TF_DIR" output -raw frontend_bucket)"
DISTRIBUTION_ID="$(terraform -chdir="$TF_DIR" output -raw cloudfront_distribution_id)"
ECR_REPO="$(terraform -chdir="$TF_DIR" output -raw ecr_repository_url)"

log "Building and pushing the backend image"
aws ecr get-login-password --region "$AWS_REGION" \
  | docker login --username AWS --password-stdin "${ECR_REPO%%/*}"
docker build --platform linux/amd64 -f "$ROOT/backend/Dockerfile" -t "$ECR_REPO:latest" "$ROOT/backend"
docker push "$ECR_REPO:latest"

log "Restarting the backend service"
INSTANCE_ID="$(terraform -chdir="$TF_DIR" output -raw backend_instance_id)"
aws ssm send-command \
  --instance-ids "$INSTANCE_ID" \
  --document-name "AWS-RunShellScript" \
  --parameters 'commands=["cd /opt/safespare && docker compose pull && docker compose up -d"]' \
  --region "$AWS_REGION" >/dev/null

log "Building the frontend"
( cd "$ROOT/frontend" && VITE_API_BASE_URL="https://$BACKEND_HOST" npm ci && npm run build )

log "Uploading the frontend"
# Hashed assets are immutable; index.html must never be cached or a deploy is invisible.
aws s3 sync "$ROOT/frontend/dist" "s3://$FRONTEND_BUCKET" --delete \
  --cache-control "public,max-age=31536000,immutable" --exclude "index.html"
aws s3 cp "$ROOT/frontend/dist/index.html" "s3://$FRONTEND_BUCKET/index.html" \
  --cache-control "no-cache,no-store,must-revalidate"
aws cloudfront create-invalidation --distribution-id "$DISTRIBUTION_ID" --paths "/*" >/dev/null

log "Smoke testing"
"$ROOT/infra/scripts/smoke-test.sh" "https://$BACKEND_HOST" || die "smoke test failed"

terraform -chdir="$TF_DIR" output
log "Deploy complete"
