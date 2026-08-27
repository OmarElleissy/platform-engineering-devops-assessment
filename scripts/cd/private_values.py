"""Extract validated private Terraform values into GitHub environment files."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from common import (
    PolicyError,
    append_github_values,
    container_images,
    find_one_address,
    find_one_resource,
    load_json,
    mask_value,
    require,
    require_ipv4_cidr,
    require_sha,
)

NAME_PREFIX = "platform-assessment"
EXPECTED_NAMES = {
    "ECR_REPOSITORY_NAME": f"{NAME_PREFIX}-app",
    "ECS_CLUSTER_NAME": f"{NAME_PREFIX}-cluster",
    "ECS_SERVICE_NAME": f"{NAME_PREFIX}-service",
    "CLOUDWATCH_LOG_GROUP_NAME": f"/ecs/{NAME_PREFIX}",
}


def output_value(outputs: dict[str, Any], name: str) -> str:
    """Extract one string from redirected `terraform output -json` data."""
    item = outputs.get(name)
    require(isinstance(item, dict), f"required Terraform output is missing: {name}")
    value = item.get("value")
    require(isinstance(value, str) and value, f"Terraform output is invalid: {name}")
    return value


def extract_outputs(document: dict[str, Any]) -> dict[str, str]:
    """Validate application outputs and return private environment values."""
    values = {
        "ECR_REPOSITORY_NAME": output_value(document, "ecr_repository_name"),
        "ECR_REPOSITORY_URL": output_value(document, "ecr_repository_url"),
        "ECS_CLUSTER_NAME": output_value(document, "ecs_cluster_name"),
        "ECS_SERVICE_NAME": output_value(document, "ecs_service_name"),
        "APPLICATION_URL": output_value(document, "application_url"),
        "CLOUDWATCH_LOG_GROUP_NAME": output_value(
            document, "cloudwatch_log_group_name"
        ),
    }
    for key, expected in EXPECTED_NAMES.items():
        require(
            values[key] == expected, f"unexpected deterministic Terraform output: {key}"
        )

    repository_url = values["ECR_REPOSITORY_URL"]
    repository_pattern = re.compile(
        r"^[0-9]{12}\.dkr\.ecr\.eu-central-1\.amazonaws\.com/"
        r"platform-assessment-app$"
    )
    require(
        repository_pattern.fullmatch(repository_url) is not None,
        "invalid ECR repository URL",
    )
    values["ECR_REGISTRY"] = repository_url.split("/", 1)[0]

    parsed_url = urlparse(values["APPLICATION_URL"])
    require(parsed_url.scheme == "http", "application URL must use assessment HTTP")
    require(
        parsed_url.port is None and parsed_url.path in ("", "/"),
        "invalid application URL",
    )
    require(
        parsed_url.hostname is not None
        and parsed_url.hostname.endswith(".eu-central-1.elb.amazonaws.com"),
        "application URL is not the expected regional ALB endpoint",
    )
    return values


def extract_state(document: dict[str, Any], expected_sha: str) -> dict[str, str]:
    """Extract only the state values required for deploy validation or destroy."""
    sha = require_sha(expected_sha, "expected deployed SHA")
    task = find_one_resource(document, "aws_ecs_task_definition")
    images = container_images(task)
    require(
        len(images) == 1 and images[0].endswith(f":{sha}"),
        "state image tag differs from expected SHA",
    )

    ingress = find_one_address(document, "aws_vpc_security_group_ingress_rule.alb_http")
    cidr = require_ipv4_cidr(ingress.get("values", {}).get("cidr_ipv4", ""))

    repository = find_one_resource(document, "aws_ecr_repository")
    cluster = find_one_resource(document, "aws_ecs_cluster")
    service = find_one_resource(document, "aws_ecs_service")
    target_group = find_one_resource(document, "aws_lb_target_group")
    log_group = find_one_resource(document, "aws_cloudwatch_log_group")

    values = {
        "CURRENT_IMAGE_SHA": sha,
        "CURRENT_ALLOWED_CIDR": cidr,
        "ECR_REPOSITORY_NAME": repository.get("values", {}).get("name", ""),
        "ECS_CLUSTER_NAME": cluster.get("values", {}).get("name", ""),
        "ECS_SERVICE_NAME": service.get("values", {}).get("name", ""),
        "TARGET_GROUP_ARN": target_group.get("values", {}).get("arn", ""),
        "CLOUDWATCH_LOG_GROUP_NAME": log_group.get("values", {}).get("name", ""),
    }
    for key, expected in EXPECTED_NAMES.items():
        if key in values:
            require(
                values[key] == expected,
                f"state contains unexpected resource identity: {key}",
            )
    require(
        re.fullmatch(
            r"arn:[a-z0-9-]+:elasticloadbalancing:[^:]+:[0-9]{12}:targetgroup/.+",
            values["TARGET_GROUP_ARN"],
        )
        is not None,
        "state target-group ARN is invalid",
    )
    return values


def write_private_values(values: dict[str, str], destination: str | Path) -> None:
    """Mask all selected identifiers before appending them to GitHub's env file."""
    require(
        all(isinstance(value, str) and value for value in values.values()),
        "private value is empty",
    )
    for value in dict.fromkeys(values.values()):
        mask_value(value)
    append_github_values(destination, values)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--kind", required=True, choices=("outputs", "state"))
    parser.add_argument("--json", required=True)
    parser.add_argument("--github-env", required=True)
    parser.add_argument("--expected-sha")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        document = load_json(args.json)
        require(isinstance(document, dict), "private Terraform JSON must be an object")
        if args.kind == "outputs":
            values = extract_outputs(document)
        else:
            require(
                args.expected_sha is not None, "state extraction requires expected SHA"
            )
            values = extract_state(document, args.expected_sha)
        write_private_values(values, args.github_env)
    except PolicyError as exc:
        print(f"Private Terraform value policy failed: {exc}", file=sys.stderr)
        return 1
    print("Private Terraform values validated and masked")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
