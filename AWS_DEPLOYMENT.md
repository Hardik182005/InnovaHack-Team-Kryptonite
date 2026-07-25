# AWS_DEPLOYMENT.md

> **Nothing has been deployed. Nothing has been validated by Terraform.**
> `terraform` and the `aws` CLI are not installed on the development machine
> (verified with `command -v terraform aws` — neither found). Per spec §3.24 and
> testing-prompt §2.16, no deployment success is claimed anywhere in this repo.
>
> What *has* been verified: the Docker image builds and runs, and
> `infra/scripts/smoke-test.sh` passes 16/16 against that running container.

---

## 1. Architecture (§21)

Low-cost, single-region, hackathon scale.

```
                    ┌──────────────┐
   browser ────────▶│  CloudFront  │──────▶ S3 (frontend, private + OAC)
                    └──────┬───────┘
                           │ /api/*
                    ┌──────▼───────────────┐
                    │ EC2 t4g.small        │  Caddy (auto-HTTPS)
                    │ public subnet, no NAT │──▶ FastAPI in Docker
                    └──────┬───────────────┘
                           ├──▶ S3 (uploads, private, lifecycle-deleted)
                           ├──▶ DynamoDB (on-demand, TTL)
                           └──▶ SSM Parameter Store (SecureString)
```

**Deliberately excluded:** GPU instances, Kubernetes, **NAT Gateway**, load
balancer, RDS, multiple always-on environments. Each is a recurring cost this
project does not need, and the NAT Gateway alone would exceed the compute bill.

| Concern | Choice | Why |
| --- | --- | --- |
| Frontend | S3 + CloudFront | static SPA, pennies at this scale |
| Backend | one t4g.small (ARM) | enough RAM for MiniLM; cheapest option that fits |
| TLS | Caddy | automatic certificates, no ALB cost |
| Database | DynamoDB on-demand | no idle cost; TTL expires temporary analyses |
| Secrets | SSM SecureString | free tier; never in an image layer or in Git |
| Egress | public subnet, no NAT | a NAT Gateway would cost more than everything else combined |

## 2. Files

```
infra/terraform/
  providers.tf   variables.tf   main.tf
  storage.tf     database.tf    compute.tf
  iam.tf         monitoring.tf  outputs.tf
infra/scripts/
  deploy.sh      update.sh      rollback.sh
  destroy.sh     seed-demo.sh   smoke-test.sh   ← verified working
```

## 3. Prerequisites

```bash
brew install terraform awscli      # neither is present on the dev machine
aws configure sso                  # or aws configure
aws sts get-caller-identity        # must succeed before deploying
```

## 4. Deploy

```bash
export AWS_REGION=ap-south-1
export ENVIRONMENT=dev

terraform -chdir=infra/terraform init
terraform -chdir=infra/terraform fmt -check
terraform -chdir=infra/terraform validate
terraform -chdir=infra/terraform plan -var="environment=$ENVIRONMENT"
#   ^ inspect this plan manually before applying (testing-prompt §38)

bash infra/scripts/deploy.sh
```

`deploy.sh` applies the plan, builds and pushes the backend image, restarts the
service over SSM, builds and uploads the frontend, invalidates CloudFront, and
finishes by running `smoke-test.sh` against the deployed URL. It aborts if the
smoke test fails.

## 5. Ship code without touching infrastructure

```bash
bash infra/scripts/update.sh backend    # runs pytest first; refuses to ship on failure
bash infra/scripts/update.sh frontend   # runs tsc first
bash infra/scripts/update.sh            # both
```

## 6. Roll back / tear down

```bash
bash infra/scripts/rollback.sh <image-tag>
bash infra/scripts/destroy.sh           # removes every resource
```

Run `destroy.sh` when the hackathon ends. DynamoDB on-demand and S3 cost
essentially nothing at rest, but the EC2 instance bills hourly regardless of use.

## 7. Cost safety

- No NAT Gateway, no load balancer, no GPU, no Kubernetes
- One backend instance; stop it when not demoing
- S3 lifecycle deletes uploaded statements automatically
- DynamoDB TTL expires temporary analyses
- Set a budget alert before deploying:

```bash
aws budgets create-budget --account-id "$(aws sts get-caller-identity --query Account --output text)" \
  --budget '{"BudgetName":"safespare","BudgetLimit":{"Amount":"20","Unit":"USD"},"TimeUnit":"MONTHLY","BudgetType":"COST"}'
```

## 8. Security checklist (§38)

Reviewed by inspection; **not** verified by `terraform plan`.

| Requirement | Status |
| --- | --- |
| S3 buckets block all public access | written |
| CloudFront uses OAC, not a public bucket | written |
| Encryption at rest on S3 and DynamoDB | written |
| S3 lifecycle deletion present | written |
| HTTPS in production | Caddy auto-TLS |
| Port 22 not open to 0.0.0.0/0 | SSM Session Manager; no open SSH |
| Database not publicly reachable | DynamoDB via IAM only |
| Secrets not in Terraform variables | SSM SecureString, read at runtime |
| Least-privilege IAM | scoped to specific bucket prefix, tables, SSM path |
| Terraform state | **⚠ configure a remote encrypted backend before real use** — local state is the default and must not hold production state |

## 9. Post-deployment verification (§39)

```bash
bash infra/scripts/smoke-test.sh https://<backend-domain>
```

Checks health, readiness, OpenAPI, a full demo analysis to `COMPLETED`, all seven
read endpoints, cross-session isolation, that Safe Spare is never negative, and
that deletion actually removes data. Then manually confirm:

- CloudWatch logs contain no account numbers or secrets
- S3 objects are private
- the lifecycle policy is attached
- the mobile layout works on the deployed URL

## 10. Status

| Item | Status |
| --- | --- |
| Terraform written | ✅ 9 files |
| Shell scripts written | ✅ 6, all pass `bash -n` |
| Docker image | ✅ builds, runs, 16/16 smoke tests |
| `terraform validate` | ❌ **BLOCKED** — not installed |
| `terraform plan` | ❌ **BLOCKED** — not installed |
| Deployed | ❌ **NO** |
| Frontend URL | none |
| Backend URL | none |
