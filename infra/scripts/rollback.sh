#!/usr/bin/env bash
#
# SafeSpare AI — roll the deployed application back to a previous version.
#
# This rolls back APPLICATION artifacts, never infrastructure. Terraform
# state is left alone: reverting infra means checking out the older .tf files
# and running deploy.sh, which is a deliberate, reviewable act rather than
# something a rollback script should do to you mid-demo.
#
#   ./infra/scripts/rollback.sh                       # list what you can roll back to
#   ./infra/scripts/rollback.sh backend <image-tag>   # repoint :latest and restart
#   ./infra/scripts/rollback.sh frontend              # restore previous S3 object versions
#
# The backend path works because deploy.sh/update.sh push every build under an
# immutable <git-sha>-<timestamp> tag as well as :latest. The frontend path
# works because the frontend bucket has S3 versioning enabled (storage.tf).
#
# NOTE (honesty flag): authored on a machine with neither `terraform` nor the
# `aws` CLI installed. `bash -n` clean; never executed against real AWS.

set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/_lib.sh"

TARGET="${1:-list}"

log "Preflight"
require_cmd terraform
require_aws_credentials

ECR_REPO_URL="$(tf_output ecr_repository_url)"
ECR_REGISTRY="${ECR_REPO_URL%%/*}"
ECR_REPO_NAME="${ECR_REPO_URL##*/}"
AWS_REGION="$(printf '%s' "${ECR_REGISTRY}" | cut -d. -f4)"
[[ -n "${AWS_REGION}" ]] || AWS_REGION="$(aws configure get region 2>/dev/null || echo us-east-1)"

######################################################################
# list — show the available rollback points
######################################################################

if [[ "${TARGET}" == "list" ]]; then
  log "Backend images in ${ECR_REPO_NAME} (newest first)"
  aws ecr describe-images \
    --repository-name "${ECR_REPO_NAME}" \
    --region "${AWS_REGION}" \
    --query 'sort_by(imageDetails,&imagePushedAt)[*].{Pushed:imagePushedAt,Tags:imageTags,MB:imageSizeInBytes}' \
    --output table

  echo
  log "Roll back with:"
  echo "  ./infra/scripts/rollback.sh backend  <image-tag>"
  echo "  ./infra/scripts/rollback.sh frontend"
  exit 0
fi

######################################################################
# backend — retag an older image as :latest, then restart the container
######################################################################

if [[ "${TARGET}" == "backend" ]]; then
  ROLLBACK_TAG="${2:-}"
  [[ -n "${ROLLBACK_TAG}" ]] \
    || die "Usage: ./infra/scripts/rollback.sh backend <image-tag>   (run with no arguments to list tags)"
  [[ "${ROLLBACK_TAG}" != "latest" ]] \
    || die "'latest' is the tag you are rolling back FROM. Pass an immutable <git-sha>-<timestamp> tag."

  require_cmd docker
  INSTANCE_ID="$(tf_output backend_instance_id)"
  HEALTH_URL="$(tf_output backend_health_url)"

  log "Confirming ${ROLLBACK_TAG} exists in ECR"
  aws ecr describe-images \
    --repository-name "${ECR_REPO_NAME}" \
    --image-ids "imageTag=${ROLLBACK_TAG}" \
    --region "${AWS_REGION}" >/dev/null \
    || die "Image tag '${ROLLBACK_TAG}' not found in ${ECR_REPO_NAME}."

  confirm "Repoint ${ECR_REPO_NAME}:latest at ${ROLLBACK_TAG} and restart the backend?"

  # Retag server-side by re-putting the existing manifest under :latest. This
  # needs no local pull and no re-push of layers, so it is fast and cannot
  # accidentally ship a locally-modified image.
  log "Retagging ${ROLLBACK_TAG} as latest"
  MANIFEST="$(aws ecr batch-get-image \
    --repository-name "${ECR_REPO_NAME}" \
    --image-ids "imageTag=${ROLLBACK_TAG}" \
    --region "${AWS_REGION}" \
    --query 'images[0].imageManifest' --output text)"
  [[ -n "${MANIFEST}" && "${MANIFEST}" != "None" ]] || die "Could not read the image manifest for ${ROLLBACK_TAG}."

  aws ecr put-image \
    --repository-name "${ECR_REPO_NAME}" \
    --image-tag latest \
    --image-manifest "${MANIFEST}" \
    --region "${AWS_REGION}" >/dev/null 2>&1 \
    || warn "put-image reported an error — usually 'ImageAlreadyExists', which means :latest already points here."
  ok ":latest now points at ${ROLLBACK_TAG}"

  remote_refresh "${INSTANCE_ID}" "${AWS_REGION}"

  if wait_for_health "${HEALTH_URL}" 20 5; then
    ok "Rolled back to ${ROLLBACK_TAG} and healthy: ${HEALTH_URL}"
  else
    die "Still unhealthy after rollback. Get a shell and look: aws ssm start-session --target ${INSTANCE_ID} --region ${AWS_REGION}"
  fi
  exit 0
fi

######################################################################
# frontend — restore the previous version of every object in the bucket
######################################################################

if [[ "${TARGET}" == "frontend" ]]; then
  require_cmd python3 "Needed to parse the S3 version listing."
  FRONTEND_BUCKET="$(tf_output frontend_bucket)"
  DISTRIBUTION_ID="$(tf_output cloudfront_distribution_id)"
  FRONTEND_URL="$(tf_output frontend_url)"

  log "Reading object versions in s3://${FRONTEND_BUCKET}"
  VERSIONS_JSON="$(mktemp)"
  # shellcheck disable=SC2064  # expand FRONTEND_BUCKET/VERSIONS_JSON now, on purpose
  trap "rm -f '${VERSIONS_JSON}'" EXIT

  aws s3api list-object-versions \
    --bucket "${FRONTEND_BUCKET}" \
    --region "${AWS_REGION}" \
    --output json > "${VERSIONS_JSON}"

  # For each key, find the newest NON-current version — that is the previous
  # deploy. Delete markers are skipped: a key whose current state is "deleted"
  # was removed by `s3 sync --delete` and should stay removed.
  PLAN="$(python3 - "${VERSIONS_JSON}" <<'PY'
import json, sys

with open(sys.argv[1]) as fh:
    doc = json.load(fh)

by_key = {}
for v in doc.get("Versions", []):
    if v.get("IsLatest"):
        continue
    key = v["Key"]
    prev = by_key.get(key)
    if prev is None or v["LastModified"] > prev["LastModified"]:
        by_key[key] = v

for key, v in sorted(by_key.items()):
    print(f'{key}\t{v["VersionId"]}')
PY
)"

  if [[ -z "${PLAN}" ]]; then
    die "No previous object versions found. This looks like the first frontend deploy — there is nothing to roll back to."
  fi

  echo
  log "Objects that would be restored to their previous version:"
  printf '%s\n' "${PLAN}" | awk -F'\t' '{printf "    %s\n", $1}'
  echo
  confirm "Restore $(printf '%s\n' "${PLAN}" | wc -l | tr -d ' ') object(s) to their previous version?"

  while IFS=$'\t' read -r key version_id; do
    [[ -n "${key}" ]] || continue
    log "Restoring ${key} (version ${version_id})"
    aws s3api copy-object \
      --bucket "${FRONTEND_BUCKET}" \
      --key "${key}" \
      --copy-source "${FRONTEND_BUCKET}/${key}?versionId=${version_id}" \
      --metadata-directive COPY \
      --region "${AWS_REGION}" >/dev/null
  done <<< "${PLAN}"

  log "Invalidating CloudFront"
  aws cloudfront create-invalidation \
    --distribution-id "${DISTRIBUTION_ID}" \
    --paths "/*" \
    --query 'Invalidation.Id' --output text >/dev/null

  ok "Frontend rolled back: ${FRONTEND_URL} (allow a few minutes for the CDN)"
  exit 0
fi

die "Unknown target '${TARGET}'. Use: list | backend <image-tag> | frontend"
