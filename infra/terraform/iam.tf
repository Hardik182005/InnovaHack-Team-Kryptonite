######################################################################
# SafeSpare AI — IAM (least privilege) + SSM Parameter Store secrets
#
# The EC2 instance role is scoped to exactly three things:
#   - the uploads S3 bucket (its objects only, not the whole account's S3)
#   - the two DynamoDB tables this app owns (+ their indexes)
#   - the SSM parameter path prefix this app owns
# plus the two AWS-managed policies required for keyless operations:
#   - AmazonSSMManagedInstanceCore, so `aws ssm start-session` works with no
#     open port 22 and no key pair (this is the accepted, standard exception
#     to hand-rolled least privilege — it's what makes enable_ssh=false safe)
#   - ECR pull permissions, scoped to just this app's repository below
######################################################################

######################################################################
# SSM Parameter Store — secrets, created as placeholders
#
# Terraform creates these parameters with a placeholder value so the path
# exists and IAM can be scoped to it. `lifecycle.ignore_changes` on `value`
# means a human sets the real secret once via:
#   aws ssm put-parameter --name <name> --value <real-value> --type SecureString --overwrite
# and a subsequent `terraform apply` will NOT stomp it back to the
# placeholder. Real values are never written to Git or Terraform state
# beyond this intentional placeholder.
######################################################################

# The AWS-managed key that encrypts SecureString parameters. Looked up (not
# hardcoded) because the key ID differs per account and region.
data "aws_kms_alias" "ssm" {
  name = "alias/aws/ssm"
}

locals {
  ssm_secret_params = [
    "OPENAI_API_KEY",
    "GEMINI_API_KEY",
    "GROQ_API_KEY",
    "ELEVENLABS_API_KEY",
  ]

  # name => placeholder value. LOCAL_EMBEDDING_MODEL gets a real default
  # per spec §15; the rest are non-secret config that still benefits from
  # living in SSM (one source of config truth, no .env to hand-copy).
  ssm_config_params = {
    OPENAI_MODEL          = "REPLACE_ME"
    OPENAI_FALLBACK_MODEL = "REPLACE_ME"
    GEMINI_MODEL          = "REPLACE_ME"
    GEMINI_FALLBACK_MODEL = "REPLACE_ME"
    GROQ_MODEL            = "REPLACE_ME"
    GROQ_FALLBACK_MODEL   = "REPLACE_ME"
    ELEVENLABS_VOICE_ID   = "REPLACE_ME"
    ELEVENLABS_MODEL_ID   = "REPLACE_ME"
    LOCAL_EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"

    # The app's own CORS allow-list (FastAPI CORSMiddleware), not the uploads
    # bucket's. Driven by the same var as the bucket rule so the two cannot
    # drift apart. Without this the backend falls back to its localhost-only
    # default and rejects the deployed frontend's origin outright.
    CORS_ALLOW_ORIGINS = join(",", var.cors_allowed_origins)
  }

  ssm_path_prefix = "/${local.name_prefix}"
}

resource "aws_ssm_parameter" "secret" {
  for_each = toset(local.ssm_secret_params)

  name  = "${local.ssm_path_prefix}/${each.value}"
  type  = "SecureString"
  value = "REPLACE_ME"
  # SSM rejects anything outside [\p{L}\p{LD}\p{Z}\p{N}_.:/=+\-@] here, which
  # rules out the em-dash, backticks, commas and semicolons used elsewhere.
  description = "SafeSpare AI ${each.value} placeholder. Set the real value with aws ssm put-parameter --overwrite."

  tags = local.common_tags

  lifecycle {
    ignore_changes = [value]
  }
}

resource "aws_ssm_parameter" "config" {
  for_each = local.ssm_config_params

  name        = "${local.ssm_path_prefix}/${each.key}"
  type        = "String"
  value       = each.value
  description = "SafeSpare AI ${each.key}."

  tags = local.common_tags

  lifecycle {
    ignore_changes = [value]
  }
}

######################################################################
# EC2 instance role
######################################################################

data "aws_iam_policy_document" "ec2_assume_role" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["ec2.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "backend" {
  name               = "${local.name_prefix}-backend-role"
  assume_role_policy = data.aws_iam_policy_document.ec2_assume_role.json

  tags = local.common_tags
}

resource "aws_iam_instance_profile" "backend" {
  name = "${local.name_prefix}-backend-profile"
  role = aws_iam_role.backend.name
}

# Keyless shell access via SSM Session Manager instead of opening port 22.
resource "aws_iam_role_policy_attachment" "ssm_core" {
  role       = aws_iam_role.backend.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

data "aws_iam_policy_document" "backend_scoped" {
  statement {
    sid    = "UploadsBucketObjectAccess"
    effect = "Allow"
    actions = [
      "s3:GetObject",
      "s3:PutObject",
      "s3:DeleteObject",
    ]
    resources = ["${aws_s3_bucket.uploads.arn}/*"]
  }

  statement {
    sid       = "UploadsBucketListAccess"
    effect    = "Allow"
    actions   = ["s3:ListBucket"]
    resources = [aws_s3_bucket.uploads.arn]
  }

  statement {
    sid    = "DynamoDbTableAccess"
    effect = "Allow"
    actions = [
      "dynamodb:GetItem",
      "dynamodb:PutItem",
      "dynamodb:UpdateItem",
      "dynamodb:DeleteItem",
      "dynamodb:Query",
      "dynamodb:BatchGetItem",
      "dynamodb:BatchWriteItem",
    ]
    resources = [
      aws_dynamodb_table.analyses.arn,
      "${aws_dynamodb_table.analyses.arn}/index/*",
      aws_dynamodb_table.users.arn,
      "${aws_dynamodb_table.users.arn}/index/*",
    ]
  }

  statement {
    sid    = "SsmParameterReadAccess"
    effect = "Allow"
    actions = [
      "ssm:GetParameter",
      "ssm:GetParameters",
      "ssm:GetParametersByPath",
    ]
    # Two ARNs, not one. GetParameter/GetParameters authorize against the
    # individual parameter (".../parameter/safespare-demo/GROQ_API_KEY"), but
    # GetParametersByPath authorizes against the *path* itself
    # (".../parameter/safespare-demo", with no trailing slash or wildcard).
    # Granting only the "/*" form makes refresh.sh's get-parameters-by-path
    # call fail with AccessDenied and silently produce an empty app.env.
    resources = [
      "arn:aws:ssm:${var.aws_region}:${data.aws_caller_identity.current.account_id}:parameter${local.ssm_path_prefix}",
      "arn:aws:ssm:${var.aws_region}:${data.aws_caller_identity.current.account_id}:parameter${local.ssm_path_prefix}/*",
    ]
  }

  # SecureString parameters are encrypted with the AWS-managed `alias/aws/ssm`
  # key; decrypting them via ssm:GetParameter requires this in addition to
  # the SSM permission above. IAM resource matching for KMS needs the *key*
  # ARN - an alias ARN never matches and the grant is silently useless - so
  # resolve the alias to its target key.
  statement {
    sid       = "SsmSecureStringDecrypt"
    effect    = "Allow"
    actions   = ["kms:Decrypt"]
    resources = [data.aws_kms_alias.ssm.target_key_arn]

    condition {
      test     = "StringEquals"
      variable = "kms:ViaService"
      values   = ["ssm.${var.aws_region}.amazonaws.com"]
    }
  }

  statement {
    sid    = "CloudWatchLogsWrite"
    effect = "Allow"
    actions = [
      "logs:CreateLogGroup",
      "logs:CreateLogStream",
      "logs:PutLogEvents",
    ]
    resources = ["${aws_cloudwatch_log_group.backend.arn}:*"]
  }

  statement {
    sid    = "EcrPullOnlyThisRepo"
    effect = "Allow"
    actions = [
      "ecr:GetDownloadUrlForLayer",
      "ecr:BatchGetImage",
      "ecr:BatchCheckLayerAvailability",
    ]
    resources = [aws_ecr_repository.backend.arn]
  }

  # ecr:GetAuthorizationToken has no resource-level permissions in AWS's
  # IAM model — it must be "*". This is a documented AWS limitation, not a
  # scope we're choosing to widen ourselves.
  statement {
    sid       = "EcrAuthToken"
    effect    = "Allow"
    actions   = ["ecr:GetAuthorizationToken"]
    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "backend_scoped" {
  name   = "${local.name_prefix}-backend-scoped-policy"
  role   = aws_iam_role.backend.id
  policy = data.aws_iam_policy_document.backend_scoped.json
}
