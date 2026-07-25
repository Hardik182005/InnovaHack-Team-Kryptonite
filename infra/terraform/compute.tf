######################################################################
# SafeSpare AI — backend compute
#
# One EC2 instance, one security group, one Elastic IP, one ECR repo.
# No load balancer, no ASG, no Kubernetes — the spec explicitly wants a
# single small CPU instance for a hackathon budget (§21).
#
# TLS: Caddy (in a container, started by user_data below) terminates
# HTTPS. If var.domain_name is blank it issues a Let's Encrypt cert for a
# free "<ip-with-dashes>.sslip.io" hostname derived from the instance's
# own Elastic IP at boot — no domain purchase required for the demo.
#
# Admin access: SSM Session Manager (`aws ssm start-session --target ...`),
# not SSH, by default (var.enable_ssh = false). No open port 22, no key
# pair required. This is why the security group below only opens 80/443.
######################################################################

locals {
  ecr_registry = "${data.aws_caller_identity.current.account_id}.dkr.ecr.${var.aws_region}.amazonaws.com"
}

# Always resolve the latest Amazon Linux 2023 AMI rather than hardcoding an
# AMI ID (which is region- and time-specific and would silently rot).
data "aws_ssm_parameter" "al2023_ami" {
  name = "/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64"
}

######################################################################
# ECR — one repository for the backend image
######################################################################

resource "aws_ecr_repository" "backend" {
  name                 = "${local.name_prefix}-backend"
  image_tag_mutability = "MUTABLE"
  force_delete         = true # hackathon disposability, see storage.tf note

  image_scanning_configuration {
    scan_on_push = true
  }

  tags = local.common_tags
}

resource "aws_ecr_lifecycle_policy" "backend" {
  repository = aws_ecr_repository.backend.name

  policy = jsonencode({
    rules = [
      {
        rulePriority = 1
        description  = "Keep only the 10 most recent images"
        selection = {
          tagStatus   = "any"
          countType   = "imageCountMoreThan"
          countNumber = 10
        }
        action = { type = "expire" }
      }
    ]
  })
}

######################################################################
# Security group — 80/443 open to the world (it's a public web service),
# 22 only if explicitly opted into
######################################################################

resource "aws_security_group" "backend" {
  name        = "${local.name_prefix}-backend-sg"
  description = "SafeSpare backend: HTTP/HTTPS in, SSH only if enable_ssh=true, all egress"
  vpc_id      = aws_vpc.main.id

  ingress {
    description = "HTTP (redirects to HTTPS at Caddy)"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    description = "HTTPS"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  dynamic "ingress" {
    for_each = var.enable_ssh ? [1] : []
    content {
      description = "SSH (opt-in only; prefer SSM Session Manager)"
      from_port   = 22
      to_port     = 22
      protocol    = "tcp"
      cidr_blocks = length(var.ssh_cidr_blocks) > 0 ? var.ssh_cidr_blocks : ["203.0.113.1/32"] # deliberately unroutable TEST-NET-3 default; set ssh_cidr_blocks to your real IP
    }
  }

  egress {
    description = "All outbound (no NAT needed - instance is in a public subnet)"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-backend-sg"
  })
}

######################################################################
# Elastic IP — stable address across instance replacement (update.sh /
# rollback.sh only touch the running container, but this survives even a
# full `terraform apply -replace` of the instance)
######################################################################

resource "aws_eip" "backend" {
  domain = "vpc"

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-backend-eip"
  })
}

resource "aws_eip_association" "backend" {
  instance_id   = aws_instance.backend.id
  allocation_id = aws_eip.backend.id
}

######################################################################
# EC2 instance
######################################################################

resource "aws_instance" "backend" {
  ami                    = data.aws_ssm_parameter.al2023_ami.value
  instance_type          = var.instance_type
  subnet_id              = aws_subnet.public[0].id
  vpc_security_group_ids = [aws_security_group.backend.id]
  iam_instance_profile   = aws_iam_instance_profile.backend.name
  key_name               = var.key_pair_name != "" ? var.key_pair_name : null

  root_block_device {
    volume_size           = var.root_volume_size_gb
    volume_type           = "gp3"
    encrypted             = true
    delete_on_termination = true
  }

  metadata_options {
    http_endpoint               = "enabled"
    http_tokens                 = "required" # IMDSv2 only
    http_put_response_hop_limit = 2
  }

  user_data_replace_on_change = true

  user_data = <<-EOF
    #!/bin/bash
    set -euo pipefail
    exec > >(tee /var/log/safespare-user-data.log) 2>&1
    echo "=== SafeSpare AI backend bootstrap starting $(date -u) ==="

    dnf update -y

    if ! command -v docker >/dev/null 2>&1; then
      dnf install -y docker
    fi
    systemctl enable --now docker

    if ! docker compose version >/dev/null 2>&1; then
      mkdir -p /usr/libexec/docker/cli-plugins
      curl -fsSL "https://github.com/docker/compose/releases/latest/download/docker-compose-linux-x86_64" \
        -o /usr/libexec/docker/cli-plugins/docker-compose
      chmod +x /usr/libexec/docker/cli-plugins/docker-compose
    fi

    mkdir -p /opt/safespare
    cd /opt/safespare

    AWS_REGION="${var.aws_region}"
    ECR_REGISTRY="${local.ecr_registry}"
    ECR_REPO_URL="${aws_ecr_repository.backend.repository_url}"
    S3_UPLOADS_BUCKET="${aws_s3_bucket.uploads.id}"
    DYNAMODB_ANALYSES_TABLE="${aws_dynamodb_table.analyses.name}"
    DYNAMODB_USERS_TABLE="${aws_dynamodb_table.users.name}"
    SSM_PATH_PREFIX="${local.ssm_path_prefix}"
    LOG_GROUP="${aws_cloudwatch_log_group.backend.name}"
    DOMAIN_NAME_OVERRIDE="${var.domain_name}"
    ACME_EMAIL="${var.acme_email}"
    EIP_ADDRESS="${aws_eip.backend.public_ip}"

    # The Elastic IP is attached by aws_eip_association AFTER this instance
    # boots, so right now the instance is still answering on its ephemeral
    # launch IP. Deriving the hostname from instance metadata here would
    # produce an sslip.io name for an address that is about to be replaced,
    # and Caddy would request a Let's Encrypt certificate for a host that no
    # longer resolves to us — the ACME HTTP-01 challenge would fail and HTTPS
    # would never come up. So: take the domain from the EIP Terraform already
    # knows, then wait for the association to land before Caddy starts.
    # (No dependency cycle — aws_eip.backend is allocated independently of
    # the instance; only aws_eip_association depends on it.)
    if [ -n "$DOMAIN_NAME_OVERRIDE" ]; then
      DOMAIN="$DOMAIN_NAME_OVERRIDE"
    else
      DOMAIN="$(echo "$EIP_ADDRESS" | tr '.' '-').sslip.io"
    fi
    echo "Backend will serve HTTPS on: https://$DOMAIN"
    echo "$DOMAIN" > /opt/safespare/domain.txt

    echo "Waiting for Elastic IP $EIP_ADDRESS to be associated with this instance..."
    for attempt in $(seq 1 60); do
      TOKEN=$(curl -s -X PUT "http://169.254.169.254/latest/api/token" -H "X-aws-ec2-metadata-token-ttl-seconds: 21600" || true)
      CURRENT_IP=$(curl -s -H "X-aws-ec2-metadata-token: $TOKEN" http://169.254.169.254/latest/meta-data/public-ipv4 || true)
      if [ "$CURRENT_IP" = "$EIP_ADDRESS" ]; then
        echo "Elastic IP associated after $attempt attempt(s)."
        break
      fi
      if [ "$attempt" -eq 60 ]; then
        # Don't hard-fail the bootstrap: the container stack is still worth
        # starting, and Caddy retries ACME on its own schedule.
        echo "WARNING: Elastic IP still not associated after 5 minutes (metadata reports '$CURRENT_IP'). Continuing; TLS issuance may be delayed."
      fi
      sleep 5
    done

    cat > /opt/safespare/.env <<ENVFILE
    AWS_REGION=$AWS_REGION
    ECR_REGISTRY=$ECR_REGISTRY
    ECR_REPO_URL=$ECR_REPO_URL
    IMAGE_TAG=latest
    S3_UPLOADS_BUCKET=$S3_UPLOADS_BUCKET
    DYNAMODB_ANALYSES_TABLE=$DYNAMODB_ANALYSES_TABLE
    DYNAMODB_USERS_TABLE=$DYNAMODB_USERS_TABLE
    SSM_PATH_PREFIX=$SSM_PATH_PREFIX
    LOG_GROUP=$LOG_GROUP
    ENVFILE

    # Pre-compute the global-options line instead of running a command
    # substitution inside the heredoc, so an empty ACME_EMAIL cannot leave a
    # stray non-zero status under `set -e`.
    if [ -n "$ACME_EMAIL" ]; then
      CADDY_EMAIL_LINE="email $ACME_EMAIL"
    else
      CADDY_EMAIL_LINE=""
    fi

    cat > /opt/safespare/Caddyfile <<CADDYFILE
    {
      $CADDY_EMAIL_LINE
    }

    $DOMAIN {
      encode gzip
      reverse_proxy backend:8000
      header {
        Strict-Transport-Security "max-age=31536000; includeSubDomains"
        X-Content-Type-Options "nosniff"
        X-Frame-Options "DENY"
        Referrer-Policy "strict-origin-when-cross-origin"
      }
    }
    CADDYFILE

    cat > /opt/safespare/docker-compose.yml <<'COMPOSE'
    services:
      backend:
        image: $${ECR_REPO_URL}:$${IMAGE_TAG}
        container_name: safespare-backend
        restart: unless-stopped
        env_file:
          - /opt/safespare/app.env
        environment:
          AWS_REGION: "$${AWS_REGION}"
          S3_UPLOADS_BUCKET: "$${S3_UPLOADS_BUCKET}"
          DYNAMODB_ANALYSES_TABLE: "$${DYNAMODB_ANALYSES_TABLE}"
          DYNAMODB_USERS_TABLE: "$${DYNAMODB_USERS_TABLE}"
          SSM_PARAMETER_PREFIX: "$${SSM_PATH_PREFIX}"
        logging:
          driver: awslogs
          options:
            awslogs-region: "$${AWS_REGION}"
            awslogs-group: "$${LOG_GROUP}"
            # awslogs-stream, not awslogs-stream-prefix: the prefix form is an
            # ECS task-definition option and the plain Docker awslogs driver
            # rejects it outright, which fails container creation.
            awslogs-stream: backend
            awslogs-create-group: "false"
        healthcheck:
          test: ["CMD", "python", "-c", "import urllib.request,sys; sys.exit(0) if urllib.request.urlopen('http://localhost:8000/health',timeout=3).status==200 else sys.exit(1)"]
          interval: 30s
          timeout: 5s
          retries: 3
          start_period: 30s

      caddy:
        image: caddy:2-alpine
        container_name: safespare-caddy
        restart: unless-stopped
        depends_on:
          - backend
        ports:
          - "80:80"
          - "443:443"
        volumes:
          - /opt/safespare/Caddyfile:/etc/caddy/Caddyfile:ro
          - caddy_data:/data
          - caddy_config:/config

    volumes:
      caddy_data:
      caddy_config:
    COMPOSE

    cat > /opt/safespare/refresh.sh <<'REFRESH'
    #!/bin/bash
    set -euo pipefail
    cd /opt/safespare

    set -a
    source /opt/safespare/.env
    set +a

    echo "Fetching config/secrets from SSM ($SSM_PATH_PREFIX)..."
    : > /opt/safespare/app.env
    aws ssm get-parameters-by-path \
      --path "$SSM_PATH_PREFIX" \
      --with-decryption \
      --recursive \
      --region "$AWS_REGION" \
      --query "Parameters[].[Name,Value]" \
      --output text | while IFS=$'\t' read -r name value; do
        key=$(basename "$name")
        printf '%s=%s\n' "$key" "$value" >> /opt/safespare/app.env
      done
    chmod 600 /opt/safespare/app.env

    echo "Logging in to ECR ($ECR_REGISTRY)..."
    aws ecr get-login-password --region "$AWS_REGION" | docker login --username AWS --password-stdin "$ECR_REGISTRY"

    echo "Pulling backend image $ECR_REPO_URL:$IMAGE_TAG ..."
    docker compose -f /opt/safespare/docker-compose.yml pull backend

    echo "Starting/updating stack..."
    docker compose -f /opt/safespare/docker-compose.yml up -d

    docker image prune -f >/dev/null 2>&1 || true
    echo "Refresh complete."
    REFRESH
    chmod +x /opt/safespare/refresh.sh

    cat > /etc/systemd/system/safespare-refresh.service <<'UNIT'
    [Unit]
    Description=SafeSpare AI backend refresh (pull secrets + docker compose up)
    After=docker.service network-online.target
    Wants=network-online.target
    Requires=docker.service

    [Service]
    Type=oneshot
    RemainAfterExit=yes
    ExecStart=/opt/safespare/refresh.sh
    TimeoutStartSec=300

    [Install]
    WantedBy=multi-user.target
    UNIT

    systemctl daemon-reload
    systemctl enable safespare-refresh.service
    systemctl start safespare-refresh.service

    echo "=== SafeSpare AI backend bootstrap finished $(date -u) ==="
  EOF

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-backend"
  })
}
