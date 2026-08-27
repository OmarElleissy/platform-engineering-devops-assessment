# Platform Engineering DevOps Service

A small FastAPI service used to demonstrate a secure, reproducible Phase 1
application and container baseline. It exposes a process-health endpoint and is
packaged as a hardened Linux container.

## Current status

**Phase 1 is implemented and validated.** The application, automated checks,
hardened container, security scans, and point-in-time evidence are complete.

**Phase 2 is implemented and lifecycle-validated.** The Terraform was
formatted, validated, security-scanned, and reviewed through plans. The
infrastructure was successfully provisioned, the application was deployed to
ECS Fargate and validated, and the temporary environment was then intentionally
destroyed. Item-level evidence gaps are marked explicitly in the sanitized
[Phase 2 evidence](evidence/phase2-aws-deployment-and-cleanup.md).

Recorded validation confirmed an active ECS service at desired/running/pending
counts `1/1/0` with a completed rollout, a running healthy Fargate task, and a
healthy ALB target. The health endpoint returned HTTP `200` with
`{"status":"healthy"}`, five additional consecutive requests also returned
`200`, and CloudWatch captured application startup and successful health
traffic. Terraform later reported `32 destroyed` during intentional cleanup.

The release-image security gate initially found two High findings in Alpine's
OpenSSL libraries. Both packages were upgraded to their fixed release, the
image was rebuilt without old build cache, and the remediated image passed the
recorded High/Critical blocking scan with zero High and zero Critical findings.
No suppression rule was used.

**Phase 3A continuous integration is implemented and successfully validated in
GitHub Actions.** Run `#2`, triggered by a push to
`feature/assessment-implementation`, completed all three CI jobs successfully
without workflow warnings or Node.js 20 deprecation warnings. This remains a
CI-only workflow: it does not authenticate to AWS or a registry, push an image,
or deploy. See the sanitized [Phase 3A CI evidence](evidence/phase3a-ci-validation.md).

**Phase 3B Kubernetes reference manifests are implemented and successfully
validated in GitHub Actions.** Run `#5`, triggered by a push to
`feature/assessment-implementation`, completed all four jobs successfully in 1
minute 10 seconds without workflow or Node.js deprecation warnings. Native
Kustomize rendering, strict schema validation, and deterministic
security-policy assertions passed. The manifests have not been deployed or
admitted by a real cluster; no Kubernetes cluster or live endpoint exists. See
the sanitized
[Phase 3B Kubernetes CI evidence](evidence/phase3b-kubernetes-ci-validation.md)
and the [Kubernetes reference deployment](k8s/README.md).

**Phase 3C Checkpoint 1 is committed and Checkpoint 2 workflow code is
implemented locally but unexecuted.** GitHub Actions run `#7` passed all four CI
jobs in 1 minute 30 seconds and validated both Terraform roots. The repository
now contains manual-only gated deploy/destroy workflows and offline fail-closed
policy scripts. The feature branch is not merged into `main`; no GitHub
Environment, secrets, OIDC configuration, AWS bootstrap, state migration,
deployment, cleanup, cost, or CD evidence exists. See the
[Phase 3C continuous-delivery design](docs/phase3c-continuous-delivery.md).

**There is currently no live endpoint.** The environment can be recreated from
the committed application and Terraform source in approximately 15–25 minutes
under normal AWS and network conditions. This is a planning estimate, not a
measured service-level agreement.

The following work remains pending and is not represented as complete:

- Configuration and first validated execution of gated Phase 3C delivery,
  including bootstrap, protected GitHub Environment, and state migration
- Multi-cloud network design and diagram
- Observability/SRE design

## Implemented Phase 1 features

- FastAPI `GET /health` endpoint
- HTTP `200` response with `{"status":"healthy"}`
- Service port `8080`
- Automated pytest coverage for the health contract
- Ruff linting
- Alpine-based Docker image
- Non-root runtime user with UID/GID `10001`
- Docker `HEALTHCHECK`
- `pip` removed from the runtime image
- Read-only root-filesystem compatibility
- All Linux capabilities dropped at runtime
- `no-new-privileges` compatibility

## Phase 2A AWS architecture

Terraform defines an ECS Fargate deployment in one VPC. A public Application
Load Balancer spans two public subnets and forwards traffic to ECS task ENIs in
two private subnets across two availability zones. The service can place its
task in either private subnet; `desired_count = 1` does not provide simultaneous
application capacity in both zones.

The design deliberately uses one NAT Gateway to reduce assessment cost, with
the accepted availability and cross-zone data-transfer tradeoff. Bootstrap
starts at `desired_count = 0` until an immutable ECR image tag exists. The ECS
execution role is limited to pulling that repository image and writing the
application's logs; there is no application task role because the service does
not call AWS APIs.

The task runs with a fixed non-root UID/GID, a read-only root filesystem, and
all Linux capabilities dropped. The temporary listener is HTTP-only with no
domain, ACM certificate, or TLS. The application now declares a partial S3
backend, but the destroyed/empty local state has not yet been migrated and no
remote backend has been created. The NAT Gateway, load balancer, public IPv4
addresses, Fargate runtime, image storage, logs, and data transfer can generate
cost. The Phase 2 environment was deliberately destroyed after validation to
limit charges and exercise the infrastructure lifecycle, subject to the ECR
non-empty safety check. Any recreation should follow the same cleanup strategy.

See [infra/README.md](infra/README.md) for the detailed Terraform workflow,
security-scan findings, bootstrap sequence, and cleanup guidance.

## Repository structure

The public repository preserves the Phase 1 files, adds the Phase 2A Terraform
configuration under `infra/`, defines Phase 3A/3B CI under
`.github/workflows/`, includes Phase 3B Kubernetes reference manifests under
`k8s/`, and adds Phase 3C repository-only CD foundations under `bootstrap/` and
`docs/`:

```text
.
├── .github/
│   └── workflows/
│       ├── cd-deploy.yml
│       ├── cd-destroy.yml
│       └── ci.yml
├── app/
│   ├── __init__.py
│   └── main.py
├── bootstrap/
│   ├── .terraform.lock.hcl
│   ├── README.md
│   ├── iam.tf
│   ├── locals.tf
│   ├── oidc.tf
│   ├── outputs.tf
│   ├── providers.tf
│   ├── state-storage.tf
│   ├── terraform.tfvars.example
│   ├── variables.tf
│   └── versions.tf
├── docs/
│   └── phase3c-continuous-delivery.md
├── evidence/
│   ├── phase2-aws-deployment-and-cleanup.md
│   ├── phase3a-ci-validation.md
│   ├── phase3b-kubernetes-ci-validation.md
│   └── security/
│       ├── README.md
│       ├── phase1-filesystem-scan.txt
│       ├── phase1-image-scan.txt
│       └── phase1-validation.txt
├── tests/
│   └── test_health.py
├── infra/
│   ├── .terraform.lock.hcl
│   ├── README.md
│   ├── alb.tf
│   ├── backend.tf
│   ├── ecr.tf
│   ├── ecs.tf
│   ├── iam.tf
│   ├── locals.tf
│   ├── logs.tf
│   ├── networking.tf
│   ├── outputs.tf
│   ├── providers.tf
│   ├── security-groups.tf
│   ├── terraform.tfvars.example
│   ├── variables.tf
│   └── versions.tf
├── k8s/
│   ├── README.md
│   ├── deployment.yaml
│   ├── kustomization.yaml
│   ├── namespace.yaml
│   ├── network-policy.yaml
│   ├── pod-disruption-budget.yaml
│   ├── service-account.yaml
│   └── service.yaml
├── scripts/
│   └── cd/
│       ├── aws_policy.py
│       ├── common.py
│       ├── ecr_policy.py
│       ├── private_values.py
│       ├── sanitize_apply.py
│       ├── terraform_plan_policy.py
│       ├── test_cd_scripts.py
│       └── validate_workflows.py
├── .dockerignore
├── .gitignore
├── Dockerfile
├── pyproject.toml
├── requirements-dev.txt
├── requirements.txt
└── README.md
```

## Prerequisites

- Git
- Python 3.12 or newer
- Docker
- Trivy
- kubectl with Kustomize support, or a standalone Kustomize binary, for
  Kubernetes reference rendering

## Local development

Create the named virtual environment and install the pinned runtime and
development dependencies:

```bash
git clone <repository-url>
cd <repository-directory>
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install --requirement requirements-dev.txt
```

Run the service locally:

```bash
uvicorn app.main:app --host 127.0.0.1 --port 8080
```

## Test, lint, and dependency validation

Run each check from the repository root:

```bash
ruff check .
python -m pytest
python -m pip check
```

## Continuous integration (Phases 3A and 3B)

The [CI workflow](.github/workflows/ci.yml) runs for pushes to `main` and
`feature/**`, for pull requests, and by manual dispatch. Concurrency control
cancels an older in-progress run for the same branch or pull request when a
newer commit arrives.

GitHub Actions run `#2` successfully completed all three jobs with no workflow
warnings or Node.js 20 deprecation warnings. The sanitized result is recorded in
the [Phase 3A CI evidence](evidence/phase3a-ci-validation.md).

The subsequent Phase 3B-enabled workflow run `#5`, triggered by a push to
`feature/assessment-implementation`, successfully completed all four jobs in 1
minute 10 seconds without workflow or Node.js deprecation warnings. The locally
resolved workflow commit is
`71ef21f1aaea0fdf253db0ca3f4d5b9a4364fcec`; the exact execution timestamp was
not recorded. See the
[Phase 3B Kubernetes CI evidence](evidence/phase3b-kubernetes-ci-validation.md).

The workflow uses Python 3.12 and caches pip downloads against both requirements
files. It installs the runtime and development dependencies, runs `pip check`,
Ruff, and pytest, and separately checks Terraform formatting before initializing
both `infra/` and `bootstrap/` without backends and validating them. It never
runs a Terraform plan or any state-changing Terraform command.

A separate Kubernetes validation job downloads checksum-verified, exactly
pinned kubectl and Kubeconform releases. It renders the Kustomization without a
cluster context, performs strict versioned schema validation, and applies
deterministic policy assertions to all six rendered resources. This job passed
in GitHub Actions without contacting a Kubernetes API server. The result is
configuration validation only: no real cluster admission, deployment, or
runtime validation occurred.

Trivy scans the checked-out repository for dependency vulnerabilities and
secrets while explicitly excluding ignored local material, Terraform state,
runtime variable files, plans, VCS data, and local tool directories. This scan
does not enable Terraform misconfiguration checks, so accepted Phase 2
architecture tradeoffs do not become unrelated SCA blockers. High or Critical
findings fail the job.

After the Python, Terraform, and Kubernetes validation jobs succeed, Buildx
builds `linux/amd64`, tags the local image with the immutable Git commit SHA,
uses GitHub Actions layer caching, and loads the image into the runner without
pushing it. Trivy scans that exact image and blocks on every High or Critical
vulnerability; no ignore file or `--ignore-unfixed` exception is used. The same
image then runs with a read-only root filesystem, all Linux capabilities
dropped, `no-new-privileges`, and port `8080` bound only to runner loopback. A
bounded retry verifies Docker health, HTTP `200`, the exact
`{"status":"healthy"}` response, and runtime UID/GID `10001:10001`. Cleanup
runs even when validation fails.

The workflow grants only `contents: read` and receives no AWS or registry
credentials because CI is intentionally isolated from delivery. Registry push
and cloud deployment remain isolated in separate manual workflows that ordinary
CI statically validates but never invokes. The Checkpoint 2 changes have not yet
run on GitHub. The previous Phase 2 AWS
deployment was performed manually and is not evidence of an executed CI/CD
deployment. Stable official action release tags are used for this assessment;
pinning every action to a reviewed full commit SHA is a recommended production
supply-chain enhancement.

## Build the Docker image

```bash
docker build --pull --tag platform-assessment:phase1 .
```

## Run the container

Normal local execution:

```bash
docker run --detach \
  --name platform-assessment \
  --publish 127.0.0.1:8080:8080 \
  platform-assessment:phase1
```

Hardened execution:

```bash
docker run --detach \
  --name platform-assessment-hardened \
  --read-only \
  --cap-drop ALL \
  --security-opt no-new-privileges:true \
  --publish 127.0.0.1:8080:8080 \
  platform-assessment:phase1
```

The service does not need a writable temporary directory for its current
workload. Add a narrowly scoped `tmpfs` only if a future dependency requires
one.

## Runtime validation

The commands below assume the hardened container is running.

Validate the endpoint contract and HTTP status:

```bash
curl --fail --silent --show-error \
  --write-out '\nHTTP %{http_code}\n' \
  http://127.0.0.1:8080/health
```

Expected output:

```text
{"status":"healthy"}
HTTP 200
```

Validate Docker health and the effective UID/GID:

```bash
docker container inspect platform-assessment-hardened \
  --format '{{.State.Health.Status}}'
docker exec platform-assessment-hardened id
```

Expected values are `healthy`, UID `10001`, and GID `10001`.

Confirm that the root filesystem rejects writes:

```bash
docker exec platform-assessment-hardened sh -c 'touch /write-test'
```

The command must fail with `Read-only file system` and a non-zero exit code.
The runtime hardening configuration can also be inspected directly:

```bash
docker container inspect platform-assessment-hardened \
  --format 'read_only={{.HostConfig.ReadonlyRootfs}} cap_drop={{json .HostConfig.CapDrop}} security_opt={{json .HostConfig.SecurityOpt}}'
```

## Trivy security scans

Scan the working tree for vulnerable dependencies, secrets, and Dockerfile
misconfigurations:

```bash
trivy filesystem \
  --scanners vuln,secret,misconfig \
  --no-progress \
  --format table \
  .
```

Run a complete vulnerability and secret scan of the image:

```bash
trivy image \
  --scanners vuln,secret \
  --no-progress \
  --format table \
  platform-assessment:phase1
```

Use a non-zero exit code to block High or Critical image vulnerabilities:

```bash
trivy image \
  --scanners vuln \
  --severity HIGH,CRITICAL \
  --exit-code 1 \
  --no-progress \
  --format table \
  platform-assessment:phase1
```

Scan results depend on the image contents and the vulnerability database at
scan time. Refresh Trivy's database and repeat the scans regularly.

## Security design

- **Non-root execution:** the image creates an unprivileged `appuser` and
  `appgroup`, both numbered `10001`, and switches to that identity permanently.
- **Minimal base:** the named Alpine Python base contains fewer OS packages than
  a general-purpose distribution, reducing image size and attack surface.
- **Runtime `pip` removal:** dependencies are installed during the build and
  `pip` is then uninstalled, reducing runtime tooling that could alter the
  environment.
- **Read-only filesystem:** the service operates without writing to its root
  filesystem and can be run with Docker's `--read-only` flag.
- **Dropped capabilities:** `--cap-drop ALL` removes ambient Linux capabilities
  that the HTTP service does not need.
- **No privilege escalation:** `no-new-privileges:true` prevents processes from
  gaining additional privileges through `execve` mechanisms.
- **Dependency pinning:** direct runtime and development dependencies use exact
  versions. Transitive dependencies are not yet hash-locked, as noted below.
- **Deny-by-default build context:** `.dockerignore` excludes everything, then
  explicitly admits only `app/` and `requirements.txt`, preventing local state,
  tests, VCS metadata, and secrets from entering the build context.

These runtime controls are supplied explicitly by the hardened `docker run`
command. Dockerfile compatibility alone does not automatically apply
`--read-only`, capability dropping, or `no-new-privileges` in every runtime.

### Vulnerability-remediation history

The first Debian Trixie-based image reported 14 High and 3 Critical inherited
findings for which fixed package versions were unavailable. Genuine Starlette
findings were remediated by upgrading the affected dependency. Separate nested
`pip` BOM findings were investigated because they misleadingly represented
packaging-tool content rather than the intended application runtime; `pip` was
removed from the finished image instead of suppressing those results.

Alpine was selected only after the complete dependency set and application were
tested for musl compatibility. The final filesystem scan, complete image scan,
and blocking High/Critical scan reported zero findings at the evidence capture
time. This is a point-in-time result, not a permanent guarantee.

### Alpine and musl tradeoffs

Alpine offers a compact package set and a smaller exposed OS surface, but it
uses musl libc rather than glibc. Some Python packages with native extensions
may lack compatible wheels, compile differently, or behave differently under
musl. The current dependency set passed tests and runtime validation on the
selected image. Every future dependency or base-image upgrade should be
retested; a slim glibc-based image may be the safer choice if compatibility or
operational support outweighs image minimization.

## Assumptions

- Commands are run from the repository root on a host capable of Linux
  containers.
- Port `8080` is available locally.
- Trivy has a current vulnerability database and can access the Docker image.
- The service is stateless and does not require runtime filesystem persistence.
- Localhost examples are for development and verification, not public exposure.
- Supported local Python versions are 3.12 or newer; the container supplies its
  own named Python runtime.

## Known limitations

- The Phase 2 environment is intentionally offline after validation and
  destruction; there is no retained cloud endpoint.
- The bootstrap completion time and summary, exact destruction-completion time,
  deployed image tag, billable cost, and several post-destroy inventory checks
  were not retained in the available sanitized evidence.
- The gated CD workflow code is implemented but has not run; bootstrap, the
  protected Environment, OIDC authentication, state migration, deployment, and
  cleanup remain unverified and incomplete.
- Native Kubernetes rendering, strict schema validation, and policy assertions
  passed in CI, but the manifests have not been admitted or deployed to a real
  cluster and no Kubernetes endpoint exists.
- The deployed assessment used plaintext HTTP without TLS or a custom domain;
  no endpoint is retained after cleanup.
- The application has a partial protected-backend declaration, but its local
  state has not been migrated and the bootstrap resources do not exist yet.
- The planned design uses one NAT Gateway and one running task, so it does not
  claim multi-AZ application availability.
- The health endpoint validates process health only; it does not check external
  dependencies, readiness, or downstream service health.
- Transitive dependencies are not yet locked with hashes.
- The base image is pinned by named version, not immutable digest.

## Future improvements and remaining phases

- Add hash-locked, reproducible transitive dependency resolution.
- Pin the verified base image by digest and automate controlled refreshes.
- Expand health semantics if the service gains external dependencies.
- Automate future Phase 2 recreation, evidence capture, and verified cleanup
  while retaining explicit approval gates for infrastructure changes.
- Configure and verify the Phase 3C prerequisites, then execute the separately
  gated deploy/destroy workflows after manual bootstrap and state migration.
- Pin GitHub Actions dependencies to reviewed full commit SHAs.
- Test admission and the reference deployment on a disposable cluster before
  any promotion.
- Add production-grade networking and observability controls, including VPC
  endpoints, flow logs, and alarms; consider customer-managed KMS encryption
  for the Terraform backend.
- Add TLS and a managed cloud endpoint during the appropriate infrastructure
  phase.

## Cleanup

Remove the normal or hardened local containers after use:

```bash
docker stop platform-assessment platform-assessment-hardened
docker rm platform-assessment platform-assessment-hardened
```

Remove local images only when they are no longer needed:

```bash
docker image rm platform-assessment:phase1
docker image rm platform-assessment:phase1-evidence
```

The Phase 1 evidence workflow intentionally keeps
`platform-assessment:phase1-evidence` available for local review.
