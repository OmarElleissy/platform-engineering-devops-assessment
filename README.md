# Platform Engineering DevOps Service

A small FastAPI service used to demonstrate a secure, reproducible Phase 1
application and container baseline. It exposes a process-health endpoint and is
packaged as a hardened Linux container.

## Current status

**Phase 1 is complete.** The application, automated checks, hardened container,
security scans, and point-in-time evidence are implemented.

The following work remains pending and is not represented as complete:

- Terraform and AWS deployment
- CI/CD
- Kubernetes reference manifests
- Networking design
- Observability design

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

## Repository structure

The public Phase 1 repository layout is:

```text
.
├── app/
│   ├── __init__.py
│   └── main.py
├── evidence/
│   └── security/
│       ├── README.md
│       ├── phase1-filesystem-scan.txt
│       ├── phase1-image-scan.txt
│       └── phase1-validation.txt
├── tests/
│   └── test_health.py
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

- Infrastructure is not implemented yet.
- CI/CD is not implemented yet.
- There is no TLS termination or cloud endpoint yet.
- The health endpoint validates process health only; it does not check external
  dependencies, readiness, or downstream service health.
- Transitive dependencies are not yet locked with hashes.
- The base image is pinned by named version, not immutable digest.

## Future improvements and remaining phases

- Add hash-locked, reproducible transitive dependency resolution.
- Pin the verified base image by digest and automate controlled refreshes.
- Expand health semantics if the service gains external dependencies.
- Implement the pending Terraform and AWS deployment phase.
- Implement CI/CD with automated tests, linting, builds, and security gates.
- Add pending Kubernetes reference manifests.
- Produce the pending networking and observability designs.
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
