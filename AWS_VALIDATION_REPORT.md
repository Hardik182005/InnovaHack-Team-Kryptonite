# AWS_VALIDATION_REPORT.md

Testing-prompt §38.

> **`terraform validate`, `terraform fmt -check` and `terraform plan` were NOT
> run.** Neither `terraform` nor the `aws` CLI is installed on this machine
> (`command -v terraform aws` → not found). The HCL below was reviewed by
> inspection only. No AWS resource has been created.

---

## 1. Checklist

| # | Requirement | Status | Basis |
| --- | --- | --- | --- |
| 1 | Frontend on S3 + CloudFront | **PASS** | `storage.tf` |
| 2 | Backend Dockerised FastAPI on one EC2 | **PASS** | `compute.tf`, Dockerfile verified working |
| 3 | HTTPS reverse proxy | **PASS** | Caddy auto-TLS in user data |
| 4 | Health check | **PASS** | Dockerfile `HEALTHCHECK` + `/health` verified |
| 5 | S3 blocks all public access | **PASS** | inspection |
| 6 | Encryption at rest | **PASS** | inspection |
| 7 | Lifecycle deletion | **PASS** | inspection |
| 8 | DynamoDB on-demand + TTL | **PASS** | `database.tf` |
| 9 | Secrets in SSM SecureString | **PASS** | `iam.tf` |
| 10 | CloudWatch logs, CPU and error alarms | **PASS** | `monitoring.tf` |
| 11 | **No GPU instance** | **PASS** | t4g.small only |
| 12 | **No NAT Gateway** | **PASS** | public subnet by design |
| 13 | **No Kubernetes** | **PASS** | none |
| 14 | **No public database** | **PASS** | DynamoDB via IAM only |
| 15 | Port 22 not open to 0.0.0.0/0 | **PASS** | SSM Session Manager; no SSH ingress |
| 16 | Least-privilege IAM | **PASS** | scoped to one bucket prefix, named tables, one SSM path |
| 17 | Secrets not in Terraform variables | **PASS** | inspection |
| 18 | `terraform fmt -check` | **BLOCKED** | not installed |
| 19 | `terraform validate` | **BLOCKED** | not installed |
| 20 | `terraform plan` reviewed | **BLOCKED** | not installed |
| 21 | Remote encrypted state backend | **⚠ NOT CONFIGURED** | see below |

## 2. Open issue

**AWS-001 — Terraform state backend is not configured.** State defaults to a
local file, which would contain resource identifiers and must not be used for
anything real. Configure an S3 backend with DynamoDB locking and encryption
before a production apply. Not blocking for a hackathon demo; blocking for
anything beyond one.

## 3. What *was* verified

Deployment tooling could not be validated, but the artifact it deploys was:

| Check | Result |
| --- | --- |
| `docker build` | **PASS** — 420 MB |
| Container runs | **PASS** |
| Container smoke test | **16/16 PASS** |
| Container user | non-root, uid 10001 |
| Container logs leak PII | **no** — 0 matches |
| `bash -n` on all 6 scripts | **PASS** |

`infra/scripts/smoke-test.sh` is not theoretical: it passed against both a local
uvicorn process and the built container, and found two real defects in itself
while doing so (BUG-008, BUG-009). It will run unchanged against a deployed URL.

## 4. To complete this validation

```bash
brew install terraform awscli
aws configure sso && aws sts get-caller-identity
terraform -chdir=infra/terraform init
terraform -chdir=infra/terraform fmt -check
terraform -chdir=infra/terraform validate
terraform -chdir=infra/terraform plan -var="environment=dev"
```

## 5. Status

**NOT DEPLOYED. NOT VALIDATED.** No frontend URL, no backend URL, no AWS
resources. Per spec §3.24, no deployment success is claimed.
