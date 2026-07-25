######################################################################
# SafeSpare AI — input variables
#
# Every variable has a sensible hackathon-scale default. Override via
# infra/terraform/terraform.tfvars (gitignored) or -var / -var-file flags.
######################################################################

variable "project_name" {
  description = "Short slug used to prefix/tag every resource. Lowercase, no spaces."
  type        = string
  default     = "safespare"
}

variable "environment" {
  description = "Deployment environment name (e.g. hackathon, demo, prod). Used in resource names and tags."
  type        = string
  default     = "hackathon"
}

variable "aws_region" {
  description = "AWS region to deploy into. us-east-1 keeps costs lowest and has the widest service availability."
  type        = string
  default     = "us-east-1"
}

######################################################################
# Networking
######################################################################

variable "vpc_cidr" {
  description = "CIDR block for the SafeSpare VPC."
  type        = string
  default     = "10.42.0.0/16"
}

variable "public_subnet_cidrs" {
  description = "CIDR blocks for the public subnets (one per AZ). No private subnets / NAT Gateway are created — everything is public-subnet + security-group-restricted, per the cost-safety requirement."
  type        = list(string)
  default     = ["10.42.0.0/24", "10.42.1.0/24"]
}

######################################################################
# Backend compute (EC2)
######################################################################

variable "instance_type" {
  description = "EC2 instance type for the backend. t3.small (2GB RAM) is the default — the MiniLM sentence-transformers model plus FastAPI/uvicorn needs headroom beyond t3.micro's 1GB. Drop to t3.micro only if you are not loading the embedding model in-process."
  type        = string
  default     = "t3.small"
}

variable "root_volume_size_gb" {
  description = "Root EBS volume size (GB) for the backend instance."
  type        = number
  default     = 20
}

variable "enable_ssh" {
  description = "Whether to open port 22 on the backend security group. Default false — admin access is via SSM Session Manager (aws ssm start-session), which needs no open inbound port and no key pair. Set true only if you specifically want traditional SSH."
  type        = bool
  default     = false
}

variable "ssh_cidr_blocks" {
  description = "CIDR blocks allowed to SSH in, only used when enable_ssh = true. Restrict this to your own IP (e.g. \"203.0.113.4/32\") — do not leave it open to the world."
  type        = list(string)
  default     = []
}

variable "key_pair_name" {
  description = "Existing EC2 key pair name for SSH, only used when enable_ssh = true. Leave blank to rely solely on SSM Session Manager."
  type        = string
  default     = ""
}

variable "domain_name" {
  description = "Optional custom domain for the backend (e.g. api.example.com), pointed at the backend Elastic IP out-of-band. Leave blank to use a free automatic HTTPS domain via sslip.io based on the instance's Elastic IP — no DNS purchase required for the demo."
  type        = string
  default     = ""
}

variable "acme_email" {
  description = "Email address given to Let's Encrypt (via Caddy) for certificate expiry notices. Optional but recommended."
  type        = string
  default     = ""
}

######################################################################
# Storage (S3)
######################################################################

variable "upload_retention_days" {
  description = "Days before an uploaded statement is automatically deleted from S3 via lifecycle rule. Keep short — these are sensitive financial documents."
  type        = number
  default     = 7
}

variable "cors_allowed_origins" {
  description = "Origins allowed to PUT directly to the uploads bucket via presigned URL (the frontend origin(s)). Update after the CloudFront distribution is created to restrict this from \"*\" to the real https://<distribution>.cloudfront.net (and/or custom domain)."
  type        = list(string)
  default     = ["*"]
}

variable "cloudfront_price_class" {
  description = "CloudFront price class. PriceClass_100 (US/Canada/Europe only) is the cheapest and is sufficient for a hackathon demo audience."
  type        = string
  default     = "PriceClass_100"
}

######################################################################
# Database (DynamoDB)
######################################################################

variable "analyses_ttl_attribute" {
  description = "Attribute name used for DynamoDB TTL on the analyses table. The application sets this to an epoch timestamp when writing temporary/analysis items so they self-delete."
  type        = string
  default     = "expires_at"
}

variable "enable_point_in_time_recovery" {
  description = "Enable DynamoDB point-in-time recovery. Adds a small storage-based cost; off by default for a disposable hackathon environment."
  type        = bool
  default     = false
}

######################################################################
# Monitoring / cost safety
######################################################################

variable "log_retention_days" {
  description = "CloudWatch Logs retention for the backend log group."
  type        = number
  default     = 14
}

variable "cpu_alarm_threshold" {
  description = "CPUUtilization percentage that triggers the high-CPU CloudWatch alarm."
  type        = number
  default     = 80
}

variable "error_alarm_threshold" {
  description = "Number of ERROR-level log lines within one 5-minute period that triggers the error-rate alarm."
  type        = number
  default     = 5
}

variable "enable_health_check" {
  description = "Create a Route 53 health check (~$0.50/month) that probes the backend's /health endpoint over HTTPS from multiple AWS regions, plus the CloudWatch alarm on it. Set false to save the half-dollar; the EC2 StatusCheckFailed alarm still runs either way."
  type        = bool
  default     = true
}

variable "health_check_path" {
  description = "Path probed by the Route 53 health check and reported by outputs.backend_health_url. Must be a public, unauthenticated endpoint that returns 2xx."
  type        = string
  default     = "/health"
}

variable "alert_email" {
  description = "Email address subscribed to the SNS alerts topic (CloudWatch alarms + budget alerts). Leave blank to skip the email subscription (alarms still fire, just with nowhere to notify — set this before a real demo)."
  type        = string
  default     = ""
}

variable "monthly_budget_usd" {
  description = "Monthly AWS budget threshold (USD) for the budget-alert guardrail."
  type        = number
  default     = 20
}

######################################################################
# Tagging
######################################################################

variable "extra_tags" {
  description = "Additional tags merged into every resource's tag set."
  type        = map(string)
  default     = {}
}
