"""Statically enforce Phase 3C workflow security policy without cloud access."""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any

import yaml
from common import PolicyError, require

ROOT = Path(__file__).resolve().parents[2]
DEPLOY_PATH = ROOT / ".github/workflows/cd-deploy.yml"
DESTROY_PATH = ROOT / ".github/workflows/cd-destroy.yml"
CI_PATH = ROOT / ".github/workflows/ci.yml"

EXPECTED = {
    DEPLOY_PATH: {
        "name": "Deploy application infrastructure",
        "job": "deploy",
        "confirmation": "DEPLOY platform-assessment",
        "inputs": {"confirmation"},
        "actions": {
            "actions/checkout@v6",
            "hashicorp/setup-terraform@v4",
            "aws-actions/configure-aws-credentials@v6.2.3",
            "aquasecurity/setup-trivy@v0.2.6",
            "docker/setup-buildx-action@v4",
            "docker/build-push-action@v7",
        },
    },
    DESTROY_PATH: {
        "name": "Destroy application infrastructure",
        "job": "destroy",
        "confirmation": "DESTROY platform-assessment",
        "inputs": {"confirmation", "expected_sha"},
        "actions": {
            "actions/checkout@v6",
            "hashicorp/setup-terraform@v4",
            "aws-actions/configure-aws-credentials@v6.2.3",
        },
    },
}

FORBIDDEN_TEXT = (
    "pull_request_target",
    "aws-access-key-id",
    "AWS_ACCESS_KEY_ID",
    "AWS_SECRET_ACCESS_KEY",
    "set -x",
    "TF_LOG",
    "ACTIONS_STEP_DEBUG",
    "ACTIONS_RUNNER_DEBUG",
    "--debug",
    "actions/upload-artifact",
    "cancel-in-progress: true",
    "0.0.0.0/0",
)


def load_workflow(path: Path) -> tuple[dict[str, Any], str]:
    """Safely load one workflow and retain its text for shell-policy checks."""
    text = path.read_text()
    document = yaml.safe_load(text)
    require(isinstance(document, dict), f"{path.name} must contain a YAML mapping")
    return document, text


def workflow_steps(document: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        step
        for job in document.get("jobs", {}).values()
        for step in job.get("steps", [])
        if isinstance(step, dict)
    ]


def validate_one(path: Path, policy: dict[str, Any]) -> None:
    """Validate one deploy/destroy workflow against the exact static policy."""
    document, text = load_workflow(path)
    require(document.get("name") == policy["name"], f"{path.name}: wrong workflow name")
    require(
        set(document.get("on", {})) == {"workflow_dispatch"},
        f"{path.name}: invalid trigger",
    )
    require(
        document.get("permissions") == {"contents": "read", "id-token": "write"},
        f"{path.name}: permissions are not minimal",
    )
    concurrency = document.get("concurrency", {})
    require(
        concurrency == {"group": "platform-assessment-aws-lifecycle", "queue": "max"},
        f"{path.name}: concurrency policy differs",
    )
    require(
        "cancel-in-progress" not in concurrency,
        f"{path.name}: cancellation is forbidden",
    )

    inputs = document["on"]["workflow_dispatch"].get("inputs", {})
    require(set(inputs) == policy["inputs"], f"{path.name}: workflow inputs differ")
    require(
        all(
            item.get("required") is True and item.get("type") == "string"
            for item in inputs.values()
        ),
        f"{path.name}: every input must be a required string",
    )
    require(
        policy["confirmation"] in text, f"{path.name}: typed confirmation is missing"
    )

    jobs = document.get("jobs", {})
    require(set(jobs) == {"preflight", policy["job"]}, f"{path.name}: unexpected jobs")
    require(
        jobs["preflight"].get("runs-on") == "ubuntu-latest",
        f"{path.name}: wrong runner",
    )
    operation = jobs[policy["job"]]
    require(operation.get("runs-on") == "ubuntu-latest", f"{path.name}: wrong runner")
    require(
        operation.get("environment") == "assessment-aws",
        f"{path.name}: wrong environment",
    )
    require(
        operation.get("needs") == "preflight",
        f"{path.name}: preflight dependency is missing",
    )
    require(
        isinstance(operation.get("timeout-minutes"), int),
        f"{path.name}: timeout missing",
    )
    require("refs/heads/main" in text, f"{path.name}: main branch guard is missing")
    require(
        "GITHUB_REF" in text, f"{path.name}: branch is not checked before credentials"
    )

    steps = workflow_steps(document)
    used_actions = {step["uses"] for step in steps if "uses" in step}
    require(used_actions == policy["actions"], f"{path.name}: action versions differ")
    setup_steps = [
        step for step in steps if step.get("uses") == "hashicorp/setup-terraform@v4"
    ]
    require(len(setup_steps) == 1, f"{path.name}: Terraform setup must occur once")
    require(
        setup_steps[0].get("with", {}).get("terraform_wrapper") is False,
        f"{path.name}: Terraform wrapper must be disabled",
    )

    configure_indexes = [
        index
        for index, step in enumerate(steps)
        if step.get("uses") == "aws-actions/configure-aws-credentials@v6.2.3"
    ]
    require(configure_indexes, f"{path.name}: OIDC configuration is missing")
    first_credential = configure_indexes[0]
    precredential_text = "\n".join(
        str(step.get("run", "")) for step in steps[:first_credential]
    )
    require(
        "GITHUB_REF" in precredential_text,
        f"{path.name}: branch guard occurs after OIDC",
    )
    require(
        policy["confirmation"] in precredential_text,
        f"{path.name}: confirmation occurs after OIDC",
    )

    cleanup = [
        step
        for step in operation.get("steps", [])
        if step.get("name") == "Clean temporary files"
    ]
    require(
        len(cleanup) == 1 and cleanup[0].get("if") == "${{ always() }}",
        f"{path.name}: always cleanup is missing",
    )
    require("${RUNNER_TEMP}" in text, f"{path.name}: runner temp is not used")
    require("TF_STATE_BUCKET" in text, f"{path.name}: backend secret is not used")
    require(
        "AWS_ROLE_ARN" in text and "AWS_ACCOUNT_ID" in text,
        f"{path.name}: environment secrets differ",
    )
    require(
        "vars.AWS_REGION" in text,
        f"{path.name}: region environment variable is missing",
    )
    require(
        re.search(r"terraform\s+-chdir=infra\s+output\s+-json", text) is not None,
        f"{path.name}: private output extraction is missing",
    )
    require(
        "terraform output\n" not in text,
        f"{path.name}: ordinary Terraform output is forbidden",
    )
    if path == DEPLOY_PATH:
        require(
            text.count("aws ecs wait services-stable") == 1,
            f"{path.name}: ECS service stability waiter must occur exactly once",
        )
        require(
            text.count("aws elbv2 wait target-in-service") == 1,
            f"{path.name}: ALB target health waiter must occur exactly once",
        )
        for required in (
            "aws ecs list-tasks",
            "aws ecs describe-tasks",
            "aws elbv2 describe-target-health",
            "expected exactly one running ECS task",
            "${APPLICATION_URL}/health",
            '\'{"status":"healthy"}\'',
        ):
            require(
                required in text, f"{path.name}: missing live validation: {required}"
            )
        require(
            "five_request_success_count" not in text,
            f"{path.name}: redundant five-request gate remains",
        )
        require(
            "aws logs filter-log-events" not in text,
            f"{path.name}: CloudWatch logs remain a blocking deployment gate",
        )
    else:
        for required in (
            "--mode scale-zero",
            "--mode destroy",
            "terraform -chdir=infra state list",
            "aws ecr describe-repositories",
            "aws elbv2 describe-load-balancers",
            "aws ecs describe-clusters",
            "aws ec2 describe-nat-gateways",
            "aws ec2 describe-addresses",
        ):
            require(required in text, f"{path.name}: missing destroy guard: {required}")
        require(
            "aws ecr batch-delete-image" not in text,
            f"{path.name}: redundant ECR batch deletion remains",
        )
        require(
            "--mode inventory" not in text and "--mode empty" not in text,
            f"{path.name}: redundant ECR inventory validation remains",
        )

    for forbidden in FORBIDDEN_TEXT:
        require(
            forbidden not in text, f"{path.name}: forbidden workflow text: {forbidden}"
        )
    require(
        re.search(r"(?:docker\s+(?:push|tag)|tags:)\s+[^\n]*:latest", text) is None,
        f"{path.name}: latest publication is forbidden",
    )
    require("workflow_call" not in text, f"{path.name}: workflow_call is forbidden")


def validate_ci_isolation() -> None:
    """Ensure ordinary CI only parses policy and cannot invoke delivery."""
    document, text = load_workflow(CI_PATH)
    require(
        set(document.get("jobs", {}))
        == {
            "quality-and-test",
            "terraform-validation",
            "kubernetes-validation",
            "build-scan-and-runtime-test",
        },
        "CI four-job structure changed",
    )
    require(
        document.get("permissions") == {"contents": "read"}, "CI permissions changed"
    )
    require(
        "aws-actions/configure-aws-credentials" not in text,
        "CI configures AWS credentials",
    )
    require("id-token: write" not in text, "CI can request an OIDC token")
    require("aws ecr" not in text and "aws sts" not in text, "CI directly accesses AWS")
    require(
        "cd-deploy.yml" not in text and "cd-destroy.yml" not in text, "CI invokes CD"
    )
    require(
        "scripts/cd/validate_workflows.py" in text,
        "CI workflow policy check is missing",
    )


def validate_all() -> None:
    for path, policy in EXPECTED.items():
        validate_one(path, policy)
    validate_ci_isolation()


def main() -> int:
    try:
        validate_all()
    except (OSError, yaml.YAMLError, PolicyError) as exc:
        print(f"CD workflow policy failed: {exc}", file=sys.stderr)
        return 1
    print("CD workflow policy passed for deploy, destroy, and cloud-isolated CI")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
