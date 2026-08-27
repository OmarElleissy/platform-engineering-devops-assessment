# Phase 3A continuous-integration validation

## Purpose

Phase 3A validates application quality, infrastructure syntax, software
composition, image security, and hardened runtime behavior without cloud or
registry credentials. It is continuous integration only and performs no image
publishing or cloud deployment.

## Execution status

| Field | Recorded value |
| --- | --- |
| Run | `#2` |
| Trigger | Push |
| Branch | `feature/assessment-implementation` |
| Result | `Success` |
| Exact execution timestamp | `Not recorded` |
| Exact duration | `Not recorded` |
| Workflow commit | `48ef9be6364306609e9f719099862fe93b25ce54` |

All three workflow jobs completed successfully:

- `Quality, tests, and repository security`
- `Terraform formatting and validation`
- `Build, scan, and hardened runtime test`

## Quality validation

The successful quality job installed the runtime and development dependencies
and ran:

- `python -m pip check`
- Ruff using the repository configuration
- pytest using the repository configuration

## Terraform validation

The successful Terraform job checked recursive formatting, initialized the
configuration with the backend disabled, and validated the configuration. It
did not run a plan, apply changes, or perform any infrastructure mutation.

## Security validation

Trivy scanned the checked-out repository for dependency vulnerabilities and
secrets. It also scanned the exact image built by the workflow for
vulnerabilities. Both gates fail on High or Critical findings. The workflow
uses no Trivy ignore file and does not use `--ignore-unfixed`; the successful
run means no blocking finding caused either security gate to fail.

## Image build

Docker Buildx built the image for `linux/amd64`, tagged it with the Git commit
SHA, and used the GitHub Actions layer cache. The image was loaded only into the
temporary job runner for scanning and runtime validation. It was not pushed or
published. The generated Docker build record is build metadata, not the
application container image.

## Hardened runtime validation

The successful runtime job started the exact built image with a read-only root
filesystem, all Linux capabilities dropped, `no-new-privileges`, and
loopback-only port exposure. It verified that:

- Docker health became `healthy`.
- `/health` returned HTTP `200`.
- The response was exactly `{"status":"healthy"}`.
- The runtime UID/GID was `10001:10001`.
- The always-run container cleanup step completed successfully.

## Permissions and credentials

The workflow grants only `contents: read`. It uses no AWS credentials, registry
credentials, static cloud secrets, or OIDC token permission. It performs no
registry push and no deployment.

## Action-runtime maintenance

The initial successful workflow execution produced Node.js 20 deprecation
annotations. Before run `#2`, the workflow moved to these Node.js 24-compatible
official action versions:

- `actions/checkout@v6`
- `actions/setup-python@v7`
- `hashicorp/setup-terraform@v4`
- `docker/setup-buildx-action@v4`
- `docker/build-push-action@v7`

Run `#2` completed successfully without Node.js 20 deprecation warnings or
other workflow warnings.

## Limitations and remaining work

- Continuous delivery remains pending.
- Registry publishing remains pending.
- AWS OIDC design remains pending.
- Cloud deployment validation from a pipeline remains pending.
- Action references use stable major tags rather than reviewed full commit
  SHAs.
- GitHub-hosted runner execution is ephemeral.
- The exact run timestamp and duration were not retained in the supplied
  evidence.
- The earlier Phase 2 AWS deployment was manual and is not pipeline-deployment
  evidence.

## Sanitization

This record excludes repository and GitHub run URLs, account identifiers, ARNs,
registry URLs, credentials, tokens, IP addresses, screenshots, and raw logs
containing identifiers.
