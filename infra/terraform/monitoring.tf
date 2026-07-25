######################################################################
# SafeSpare AI — monitoring, alarms and cost guardrails (§21, §38)
#
# NOTE (honesty flag): `terraform` is NOT installed on the machine this
# HCL was authored on. Reviewed by eye; never run through
# `terraform init` / `validate` / `plan`. See AWS_VALIDATION_REPORT.md.
#
# Four things are watched, matching §38's "CloudWatch logs / CPU alarm /
# Error alarm / Health alarm":
#
#   1. CloudWatch Logs   — the backend container ships stdout here via the
#                          awslogs Docker driver (see compute.tf user_data).
#                          The app emits one JSON object per line
#                          (backend/app/config.py JsonFormatter), which is
#                          what makes the JSON metric filter below work.
#   2. CPU alarm         — EC2 CPUUtilization over var.cpu_alarm_threshold.
#   3. Error alarm       — count of {"level":"ERROR"|"CRITICAL"} log lines.
#   4. Health alarm      — Route 53 health check hitting https://<host>/health
#                          plus an EC2 StatusCheckFailed alarm for the case
#                          where the instance itself is sick.
#
# Everything here is deliberately cheap: log retention is short, there is
# no CloudWatch agent (no custom memory/disk metrics), no dashboard, no
# Container Insights, no X-Ray. A Route 53 health check is ~$0.50/month and
# an AWS Budget is free.
######################################################################

locals {
  # The hostname Caddy will obtain a certificate for. Mirrors the logic in
  # compute.tf user_data: an explicit domain if one was supplied, otherwise
  # a free sslip.io name derived from the Elastic IP (no DNS purchase).
  backend_host = var.domain_name != "" ? var.domain_name : "${replace(aws_eip.backend.public_ip, ".", "-")}.sslip.io"
  backend_url  = "https://${local.backend_host}"
}

######################################################################
# Log group
######################################################################

resource "aws_cloudwatch_log_group" "backend" {
  name              = "/${var.project_name}/${var.environment}/backend"
  retention_in_days = var.log_retention_days

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-backend-logs"
  })
}

######################################################################
# Alert fan-out
#
# One SNS topic for every alarm. The email subscription is optional so the
# stack still applies cleanly with no address configured — the alarms fire
# either way, they just have nowhere to notify. Confirm the subscription
# from your inbox after the first apply; AWS will not deliver until you do.
######################################################################

resource "aws_sns_topic" "alerts" {
  name = "${local.name_prefix}-alerts"

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-alerts"
  })
}

resource "aws_sns_topic_subscription" "alerts_email" {
  count = var.alert_email != "" ? 1 : 0

  topic_arn = aws_sns_topic.alerts.arn
  protocol  = "email"
  endpoint  = var.alert_email
}

######################################################################
# 1. CPU alarm
######################################################################

resource "aws_cloudwatch_metric_alarm" "backend_cpu_high" {
  alarm_name        = "${local.name_prefix}-backend-cpu-high"
  alarm_description = "Backend EC2 CPUUtilization above ${var.cpu_alarm_threshold}% for 10 minutes. On a single small instance this usually means the embedding model is thrashing or a request loop is stuck."

  namespace           = "AWS/EC2"
  metric_name         = "CPUUtilization"
  statistic           = "Average"
  period              = 300
  evaluation_periods  = 2
  threshold           = var.cpu_alarm_threshold
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "missing"

  dimensions = {
    InstanceId = aws_instance.backend.id
  }

  alarm_actions = [aws_sns_topic.alerts.arn]
  ok_actions    = [aws_sns_topic.alerts.arn]

  tags = local.common_tags
}

######################################################################
# 2. Error-rate alarm
#
# The backend logs JSON (one object per line) with a "level" field, so a
# CloudWatch JSON metric filter can count error lines exactly rather than
# grepping for the substring "ERROR" and catching it inside a message body.
#
# Metric filters are free; the metric they publish counts against the
# 10-custom-metric free tier, which one metric comfortably fits inside.
######################################################################

resource "aws_cloudwatch_log_metric_filter" "backend_errors" {
  name           = "${local.name_prefix}-backend-errors"
  log_group_name = aws_cloudwatch_log_group.backend.name
  pattern        = "{ $.level = \"ERROR\" || $.level = \"CRITICAL\" }"

  metric_transformation {
    name          = "BackendErrorCount"
    namespace     = "SafeSpare/${var.environment}"
    value         = "1"
    default_value = "0"
    unit          = "Count"
  }
}

resource "aws_cloudwatch_metric_alarm" "backend_error_rate" {
  alarm_name        = "${local.name_prefix}-backend-error-rate"
  alarm_description = "More than ${var.error_alarm_threshold} ERROR/CRITICAL log lines in a 5-minute window."

  namespace           = "SafeSpare/${var.environment}"
  metric_name         = aws_cloudwatch_log_metric_filter.backend_errors.metric_transformation[0].name
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  threshold           = var.error_alarm_threshold
  comparison_operator = "GreaterThanThreshold"

  # default_value = 0 on the filter means "no logs at all" reads as zero
  # errors rather than INSUFFICIENT_DATA, so notBreaching is honest here.
  treat_missing_data = "notBreaching"

  alarm_actions = [aws_sns_topic.alerts.arn]
  ok_actions    = [aws_sns_topic.alerts.arn]

  tags = local.common_tags
}

######################################################################
# 3. Health check
#
# Route 53 probes https://<backend_host>/health from multiple AWS regions.
# This is an external, end-to-end check: it exercises DNS, the Elastic IP,
# the security group, Caddy's TLS termination and the FastAPI health route
# in one shot — which is more than an in-instance check could tell us.
#
# HealthCheckStatus is only ever published to us-east-1, regardless of
# where the rest of the stack lives, so the alarm below uses the aliased
# us-east-1 provider declared in providers.tf.
######################################################################

resource "aws_route53_health_check" "backend" {
  count = var.enable_health_check ? 1 : 0

  type              = "HTTPS"
  ip_address        = aws_eip.backend.public_ip
  fqdn              = local.backend_host # sent as SNI + Host header
  port              = 443
  resource_path     = var.health_check_path
  request_interval  = 30
  failure_threshold = 3
  measure_latency   = false # enabling this adds a per-check cost

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-backend-health"
  })
}

resource "aws_cloudwatch_metric_alarm" "backend_health" {
  count    = var.enable_health_check ? 1 : 0
  provider = aws.us_east_1

  alarm_name        = "${local.name_prefix}-backend-health"
  alarm_description = "Route 53 health check for ${local.backend_url}${var.health_check_path} is failing — the backend is unreachable or unhealthy."

  namespace           = "AWS/Route53"
  metric_name         = "HealthCheckStatus"
  statistic           = "Minimum"
  period              = 60
  evaluation_periods  = 2
  threshold           = 1
  comparison_operator = "LessThanThreshold"
  treat_missing_data  = "breaching"

  dimensions = {
    HealthCheckId = aws_route53_health_check.backend[0].id
  }

  alarm_actions = [aws_sns_topic.alerts_us_east_1.arn]
  ok_actions    = [aws_sns_topic.alerts_us_east_1.arn]

  tags = local.common_tags
}

# A CloudWatch alarm can only target an SNS topic in its own region, so the
# us-east-1 health alarm needs a us-east-1 topic. When aws_region already is
# us-east-1 this is a second topic in the same region; harmless and free
# (SNS bills per notification, not per topic), and it keeps the config from
# needing a conditional that Terraform cannot evaluate at plan time.
resource "aws_sns_topic" "alerts_us_east_1" {
  provider = aws.us_east_1

  name = "${local.name_prefix}-alerts-use1"

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-alerts-use1"
  })
}

resource "aws_sns_topic_subscription" "alerts_us_east_1_email" {
  count    = var.alert_email != "" ? 1 : 0
  provider = aws.us_east_1

  topic_arn = aws_sns_topic.alerts_us_east_1.arn
  protocol  = "email"
  endpoint  = var.alert_email
}

# Instance-level health: covers a hung kernel or failed hypervisor, which a
# Route 53 probe would report only as a generic outage.
resource "aws_cloudwatch_metric_alarm" "backend_status_check" {
  alarm_name        = "${local.name_prefix}-backend-status-check"
  alarm_description = "EC2 status check failed for the backend instance (system or instance level)."

  namespace           = "AWS/EC2"
  metric_name         = "StatusCheckFailed"
  statistic           = "Maximum"
  period              = 60
  evaluation_periods  = 2
  threshold           = 0
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "breaching"

  dimensions = {
    InstanceId = aws_instance.backend.id
  }

  alarm_actions = [aws_sns_topic.alerts.arn]
  ok_actions    = [aws_sns_topic.alerts.arn]

  tags = local.common_tags
}

######################################################################
# 4. Cost guardrail (§21 "budget-alert documentation")
#
# AWS Budgets is free for the first two budgets. Two thresholds: a warning
# at 80% of actual spend and a forecast alarm at 100%, so an accidental
# always-on resource is caught before the credit is gone rather than after.
######################################################################

resource "aws_budgets_budget" "monthly" {
  name         = "${local.name_prefix}-monthly"
  budget_type  = "COST"
  limit_amount = tostring(var.monthly_budget_usd)
  limit_unit   = "USD"
  time_unit    = "MONTHLY"

  dynamic "notification" {
    for_each = var.alert_email != "" ? [1] : []
    content {
      comparison_operator        = "GREATER_THAN"
      threshold                  = 80
      threshold_type             = "PERCENTAGE"
      notification_type          = "ACTUAL"
      subscriber_email_addresses = [var.alert_email]
    }
  }

  dynamic "notification" {
    for_each = var.alert_email != "" ? [1] : []
    content {
      comparison_operator        = "GREATER_THAN"
      threshold                  = 100
      threshold_type             = "PERCENTAGE"
      notification_type          = "FORECASTED"
      subscriber_email_addresses = [var.alert_email]
    }
  }
}
