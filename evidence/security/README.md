# Phase 1 security evidence

This directory contains the public, point-in-time validation record for Phase
1. The evidence was finalized at `2026-08-25T22:39:51Z` and is associated with:

- Git commit: `0cf2f51f1aa03d7fb4040bb798e6e0988f8f9149`
- Image tag: `platform-assessment:phase1-evidence`
- Image ID: `sha256:dd2cc3ff84ceaf88d1b852cedd38d02f1e0ab231f728a010290d0d886100471f`
- Compressed content/registry-transfer size: `23,377,843` bytes
  (approximately `23.4 MB`)
- Docker local unpacked/displayed image size: approximately `95.6 MB`
- Trivy: `0.74.0`
- Trivy vulnerability database updated: `2026-08-25T06:59:59.307495517Z`
- Trivy vulnerability database downloaded: `2026-08-25T09:40:00.618566587Z`

The tag is a convenient local name; the full image ID is the immutable
association for this evidence capture. The two size values use different
measurement methods: registry content measures compressed layers transferred,
whereas Docker's local display measures unpacked layers. They are not
contradictory.

## What each file proves

- `phase1-validation.txt` records Ruff, pytest, `pip check`, the image build,
  hardened runtime settings, endpoint response, Docker health, effective
  UID/GID, runtime `pip` removal, and the expected read-only write rejection.
- `phase1-filesystem-scan.txt` records the actual Trivy scan of the repository's
  dependency file, secrets, and Dockerfile misconfigurations. It reported zero
  findings.
- `phase1-image-scan.txt` records the actual complete image scan and the
  blocking High/Critical scan. Both reported zero findings; the blocking scan
  exited successfully.

Each text file repeats the commit, image, scanner, timestamp, command, output,
and exit-code metadata needed to interpret it independently.

## Point-in-time limitation

This evidence proves only what the named commit and image contained when tested
against the recorded Trivy database. Vulnerability intelligence, base-image
packages, dependency resolution, and local build inputs can change. A clean
result is not a permanent guarantee and must not be generalized to a later
commit or rebuilt image without rerunning the checks.

## Regeneration

From the repository root, first verify the intended commit and record metadata:

```bash
date -u +'%Y-%m-%dT%H:%M:%SZ'
git rev-parse HEAD
trivy --version
docker build --pull --tag platform-assessment:phase1-evidence .
docker image inspect platform-assessment:phase1-evidence \
  --format '{{.Id}} {{.Size}}'
docker image ls platform-assessment:phase1-evidence \
  --format 'repository={{.Repository}} tag={{.Tag}} id={{.ID}} size={{.Size}}'
```

Run the host checks and start the hardened container:

```bash
.venv/bin/ruff check .
.venv/bin/python -m pytest
.venv/bin/python -m pip check
docker run --detach \
  --name phase1-evidence-check \
  --read-only \
  --cap-drop ALL \
  --security-opt no-new-privileges:true \
  --publish 127.0.0.1:18080:8080 \
  platform-assessment:phase1-evidence
```

After Docker reports the container healthy, run the runtime checks:

```bash
curl --fail --silent --show-error \
  --write-out '\nHTTP %{http_code}\n' \
  http://127.0.0.1:18080/health
docker container inspect phase1-evidence-check \
  --format '{{.State.Health.Status}}'
docker container inspect phase1-evidence-check \
  --format 'status={{.State.Status}} running={{.State.Running}} exit={{.State.ExitCode}} health={{.State.Health.Status}} read_only={{.HostConfig.ReadonlyRootfs}} cap_drop={{json .HostConfig.CapDrop}} security_opt={{json .HostConfig.SecurityOpt}}'
docker exec phase1-evidence-check id
docker exec phase1-evidence-check python -m pip --version
docker exec phase1-evidence-check sh -c 'touch /write-test'
```

The final two commands are expected to exit non-zero: absence of `pip` and
rejection of the root-filesystem write are the passing outcomes.

Run the security scans:

```bash
trivy filesystem --scanners vuln,secret,misconfig \
  --no-progress --format table .
trivy image --scanners vuln,secret \
  --no-progress --format table platform-assessment:phase1-evidence
trivy image --scanners vuln --severity HIGH,CRITICAL --exit-code 1 \
  --no-progress --format table platform-assessment:phase1-evidence
```

Stop on any unexpected non-zero exit or unexpected output. Replace the evidence
only with output from an actual rerun, sanitizing usernames, absolute local
paths, non-loopback host addresses, credentials, tokens, account identifiers,
and private repository information. Record every exit code, then remove the
container but retain the image for review:

```bash
docker stop phase1-evidence-check
docker rm phase1-evidence-check
```
