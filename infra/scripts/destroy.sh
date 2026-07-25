#!/usr/bin/env bash
#
# SafeSpare AI — tear the whole stack down.
#
# Run this the moment the demo is over. The EC2 instance, the Elastic IP and
# the Route 53 health check bill by the hour whether anyone is looking at them
# or not, and an idle hackathon stack is the classic way to burn an AWS credit.
#
#   ./infra/scripts/destroy.sh
#   AUTO_APPROVE=1 ./infra/scripts/destroy.sh   # no prompts (CI teardown)
#
# What this deletes, permanently:
#   * every uploaded statement in the uploads bucket
#   * every analysis, transaction and goal in DynamoDB
#   * the built SPA and all of its previous versions
#   * the backend instance, its Elastic IP and its ECR images
#   * the SSM parameters, INCLUDING any real API keys you put there
#
# Both S3 buckets are force_destroy = true and the ECR repo is
# force_delete = true (storage.tf / compute.tf), so Terraform empties them
# for you rather than failing with BucketNotEmpty.
#
# NOTE (honesty flag): authored on a machine with neither `terraform` nor the
# `aws` CLI installed. `bash -n` clean; never executed against real AWS.

set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/_lib.sh"

log "Preflight"
require_cmd terraform
require_aws_credentials

######################################################################
# Show what is about to be destroyed
######################################################################

if [[ ! -d "${TF_DIR}/.terraform" ]]; then
  log "terraform init (no local .terraform directory yet)"
  terraform -chdir="${TF_DIR}" init -input=false
fi

log "Resources currently in state"
if ! terraform -chdir="${TF_DIR}" state list 2>/dev/null; then
  warn "Terraform state is empty or unreadable — there may be nothing to destroy."
fi

echo
warn "This permanently deletes:"
warn "  * all uploaded statements (S3 uploads bucket)"
warn "  * all analyses, transactions and goals (DynamoDB)"
warn "  * the built SPA and every previous version of it (S3 frontend bucket)"
warn "  * the backend EC2 instance, its Elastic IP and all ECR images"
warn "  * every SSM parameter under the project prefix, INCLUDING real API keys"
echo

######################################################################
# Two confirmations: a yes/no, then typing the project name
######################################################################

confirm "Destroy the entire SafeSpare AI stack?"

if [[ "${AUTO_APPROVE:-0}" != "1" ]]; then
  PROJECT_NAME="$(terraform -chdir="${TF_DIR}" output -raw analyses_table 2>/dev/null || echo safespare)"
  echo
  printf 'Type %s%s%s to confirm: ' "${C_BOLD}" "${PROJECT_NAME}" "${C_RESET}"
  read -r typed
  [[ "${typed}" == "${PROJECT_NAME}" ]] || die "Input did not match. Nothing was destroyed."
fi

######################################################################
# Destroy
######################################################################

log "terraform plan -destroy"
terraform -chdir="${TF_DIR}" plan -destroy -input=false -out=tfdestroyplan

log "terraform apply (destroy plan)"
terraform -chdir="${TF_DIR}" apply -input=false tfdestroyplan
rm -f "${TF_DIR}/tfdestroyplan"

ok "Stack destroyed"

######################################################################
# Local cleanup + the things Terraform cannot see
######################################################################

rm -f "${REPO_ROOT}/frontend/.env.production"
ok "Removed frontend/.env.production"

cat <<'NOTES'

Not managed by Terraform — check these by hand if you want a truly clean account:

  * CloudWatch log groups created outside this stack (the backend's own group
    IS managed and is gone).
  * The SNS email subscription confirmation you may have pending in your inbox
    (it disappears with the topic; no action needed).
  * Any S3 bucket you configured as a remote Terraform backend in
    providers.tf. That bucket is intentionally NOT part of this stack — it
    holds the state file describing the stack, so destroying it here would be
    sawing off the branch we are sitting on.
  * Verify nothing is still billing:
      aws ce get-cost-and-usage --time-period Start=$(date -u -d '2 days ago' +%Y-%m-%d 2>/dev/null || date -u -v-2d +%Y-%m-%d),End=$(date -u +%Y-%m-%d) --granularity DAILY --metrics UnblendedCost

NOTES
