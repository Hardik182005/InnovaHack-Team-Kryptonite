######################################################################
# SafeSpare AI — database (DynamoDB, on-demand billing)
#
# Two tables:
#   1. analyses — single-table design holding AnalysisSession,
#      Transaction, RecurrencePattern, PriceChange, LeakFinding,
#      UsageConfirmation, ActionDecision, SafeSpareSnapshot, RoundUpRule,
#      RoundUpCalculation, FinancialGoal, Simulation, AIInsight,
#      VoiceAsset and AuditEvent records (spec §20), all scoped under a
#      partition key per analysis session. TTL is enabled so demo/temp
#      analysis data self-deletes.
#   2. users — small, persistent (no TTL) table for the User entity.
#
# Both use PAY_PER_REQUEST billing — zero cost when idle, which matters
# for a hackathon judged intermittently rather than under constant load.
######################################################################

resource "aws_dynamodb_table" "analyses" {
  name         = "${local.name_prefix}-analyses"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "pk"
  range_key    = "sk"

  attribute {
    name = "pk"
    type = "S"
  }

  attribute {
    name = "sk"
    type = "S"
  }

  attribute {
    name = "gsi1pk"
    type = "S"
  }

  attribute {
    name = "gsi1sk"
    type = "S"
  }

  # Lets the app query "everything for user X" or "all analyses by status"
  # without scanning, e.g. gsi1pk = "USER#<user_id>", gsi1sk = "ANALYSIS#<ts>".
  global_secondary_index {
    name            = "gsi1"
    hash_key        = "gsi1pk"
    range_key       = "gsi1sk"
    projection_type = "ALL"
  }

  ttl {
    attribute_name = var.analyses_ttl_attribute
    enabled        = true
  }

  server_side_encryption {
    enabled = true
  }

  point_in_time_recovery {
    enabled = var.enable_point_in_time_recovery
  }

  tags = merge(local.common_tags, {
    Name    = "${local.name_prefix}-analyses"
    Purpose = "analysis-session-single-table"
  })
}

resource "aws_dynamodb_table" "users" {
  name         = "${local.name_prefix}-users"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "user_id"

  attribute {
    name = "user_id"
    type = "S"
  }

  server_side_encryption {
    enabled = true
  }

  point_in_time_recovery {
    enabled = var.enable_point_in_time_recovery
  }

  tags = merge(local.common_tags, {
    Name    = "${local.name_prefix}-users"
    Purpose = "user-accounts"
  })
}
