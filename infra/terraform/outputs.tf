######################################################################
# SafeSpare AI — outputs
#
# NOTE (honesty flag): `terraform` is NOT installed on the machine this
# HCL was authored on. Reviewed by eye; never run through
# `terraform init` / `validate` / `plan`. See AWS_VALIDATION_REPORT.md.
#
# NO SECRETS ARE OUTPUT HERE. Every value below is a public identifier
# (URL, bucket name, table name, ARN) that is safe to paste into a
# terminal, a README or a demo slide. API keys live only in SSM
# Parameter Store as SecureString and are never read by Terraform —
# iam.tf writes placeholders and `lifecycle.ignore_changes = [value]`
# keeps the real values out of state on subsequent applies.
#
# `terraform output` is consumed by infra/scripts/*.sh; renaming an
# output below will break those scripts.
######################################################################

######################################################################
# The two URLs a human actually needs
######################################################################

output "frontend_url" {
  description = "Public HTTPS URL of the SPA (CloudFront). This is the demo link."
  value       = "https://${aws_cloudfront_distribution.frontend.domain_name}"
}

output "backend_url" {
  description = "Public HTTPS URL of the FastAPI backend, terminated by Caddy. Uses the custom domain when var.domain_name is set, otherwise a free sslip.io hostname derived from the Elastic IP."
  value       = local.backend_url
}

output "backend_health_url" {
  description = "Backend health endpoint — the first thing to curl after a deploy."
  value       = "${local.backend_url}${var.health_check_path}"
}

output "backend_docs_url" {
  description = "OpenAPI docs served by FastAPI (§17)."
  value       = "${local.backend_url}/docs"
}

######################################################################
# Storage
######################################################################

output "frontend_bucket" {
  description = "S3 bucket holding the built SPA. Private; readable only by CloudFront via OAC. `infra/scripts/deploy.sh` syncs frontend/dist here."
  value       = aws_s3_bucket.frontend.id
}

output "uploads_bucket" {
  description = "Private S3 bucket for user-uploaded statements. Presigned-URL access only, encrypted at rest, lifecycle-expired after var.upload_retention_days days."
  value       = aws_s3_bucket.uploads.id
}

output "cloudfront_distribution_id" {
  description = "CloudFront distribution ID, needed for cache invalidation after a frontend deploy."
  value       = aws_cloudfront_distribution.frontend.id
}

######################################################################
# Database
######################################################################

output "analyses_table" {
  description = "DynamoDB single-table store for analysis sessions and their child records. On-demand billing, TTL enabled."
  value       = aws_dynamodb_table.analyses.name
}

output "users_table" {
  description = "DynamoDB table for user accounts. On-demand billing, no TTL."
  value       = aws_dynamodb_table.users.name
}

output "analyses_table_ttl_attribute" {
  description = "Attribute the application must set (epoch seconds) for a DynamoDB item to self-delete."
  value       = var.analyses_ttl_attribute
}

######################################################################
# Compute / deployment plumbing
######################################################################

output "ecr_repository_url" {
  description = "ECR repository the backend image is pushed to."
  value       = aws_ecr_repository.backend.repository_url
}

output "backend_instance_id" {
  description = "EC2 instance ID. Use with `aws ssm start-session --target <id>` for a shell — there is no open SSH port by default."
  value       = aws_instance.backend.id
}

output "backend_public_ip" {
  description = "Elastic IP of the backend instance. Point a custom A record here if you set var.domain_name."
  value       = aws_eip.backend.public_ip
}

output "ssm_session_command" {
  description = "Copy-paste command for a shell on the backend instance without SSH."
  value       = "aws ssm start-session --target ${aws_instance.backend.id} --region ${var.aws_region}"
}

######################################################################
# Configuration and secrets — PATHS ONLY, never values
######################################################################

output "ssm_parameter_prefix" {
  description = "SSM Parameter Store path holding backend config and SecureString secrets. Paths only — no values are ever output."
  value       = local.ssm_path_prefix
}

output "ssm_set_secret_example" {
  description = "Exact command shape for setting a real API key. Run it yourself; never commit the value."
  value       = "aws ssm put-parameter --name ${local.ssm_path_prefix}/OPENAI_API_KEY --type SecureString --value '<your-key>' --overwrite --region ${var.aws_region}"
}

######################################################################
# Observability
######################################################################

output "log_group_name" {
  description = "CloudWatch Logs group receiving backend container stdout."
  value       = aws_cloudwatch_log_group.backend.name
}

output "alerts_topic_arn" {
  description = "SNS topic that CloudWatch alarms publish to."
  value       = aws_sns_topic.alerts.arn
}

output "tail_logs_command" {
  description = "Copy-paste command to follow backend logs."
  value       = "aws logs tail ${aws_cloudwatch_log_group.backend.name} --follow --region ${var.aws_region}"
}

######################################################################
# Frontend build-time configuration
#
# Emitted as a block so deploy.sh can write frontend/.env.production
# before `npm run build`. Contains no secrets — Vite inlines VITE_* into
# the browser bundle, so anything here is public by construction (§22:
# "no secrets in browser bundles").
######################################################################

output "frontend_env" {
  description = "Contents for frontend/.env.production. Public values only — Vite inlines these into the JS bundle."
  value       = <<-EOT
    VITE_API_BASE_URL=${local.backend_url}
    VITE_DATA_MODE=auto
    VITE_API_TIMEOUT_MS=15000
  EOT
}

######################################################################
# Post-apply reminders
######################################################################

output "next_steps" {
  description = "What a human still has to do after `terraform apply`."
  value       = <<-EOT
    1. Set real secrets (they are placeholders until you do):
         aws ssm put-parameter --name ${local.ssm_path_prefix}/OPENAI_API_KEY --type SecureString --value '<key>' --overwrite --region ${var.aws_region}
       The app is designed to run with all of them blank (deterministic mode),
       so this step is optional for a demo.
    2. Confirm the SNS email subscription AWS just sent to ${var.alert_email == "" ? "<no alert_email set>" : var.alert_email}.
    3. Tighten CORS: re-apply with
         -var 'cors_allowed_origins=["https://${aws_cloudfront_distribution.frontend.domain_name}"]'
       The default of ["*"] is a bootstrap convenience, not a final state.
    4. Build and push the backend image, then deploy the frontend:
         ./infra/scripts/deploy.sh
    5. Verify: curl -fsS ${local.backend_url}${var.health_check_path}
  EOT
}
