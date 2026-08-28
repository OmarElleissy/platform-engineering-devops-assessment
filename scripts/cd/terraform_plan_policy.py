"""Validate private Terraform plan JSON for approved CD lifecycle transitions."""

from __future__ import annotations

import argparse
import sys
from typing import Any

from common import (
    PolicyError,
    container_images,
    find_one_address,
    find_one_resource,
    load_json,
    require,
    require_ipv4_cidr,
    require_sha,
)

EXPECTED_RESOURCES = {
    "aws_cloudwatch_log_group.app": "aws_cloudwatch_log_group",
    "aws_ecr_repository.app": "aws_ecr_repository",
    "aws_ecs_cluster.app": "aws_ecs_cluster",
    "aws_ecs_service.app": "aws_ecs_service",
    "aws_ecs_task_definition.app": "aws_ecs_task_definition",
    "aws_eip.nat": "aws_eip",
    "aws_iam_role.ecs_execution": "aws_iam_role",
    "aws_iam_role_policy.ecs_execution": "aws_iam_role_policy",
    "aws_internet_gateway.this": "aws_internet_gateway",
    "aws_lb.app": "aws_lb",
    "aws_lb_listener.http": "aws_lb_listener",
    "aws_lb_target_group.app": "aws_lb_target_group",
    "aws_nat_gateway.this": "aws_nat_gateway",
    "aws_route.private_nat": "aws_route",
    "aws_route.public_internet": "aws_route",
    "aws_route_table.private": "aws_route_table",
    "aws_route_table.public": "aws_route_table",
    "aws_route_table_association.private": "aws_route_table_association",
    "aws_route_table_association.public": "aws_route_table_association",
    "aws_security_group.alb": "aws_security_group",
    "aws_security_group.ecs": "aws_security_group",
    "aws_subnet.private": "aws_subnet",
    "aws_subnet.public": "aws_subnet",
    "aws_vpc.this": "aws_vpc",
    "aws_vpc_security_group_egress_rule.alb_to_app": (
        "aws_vpc_security_group_egress_rule"
    ),
    "aws_vpc_security_group_egress_rule.ecs_https": (
        "aws_vpc_security_group_egress_rule"
    ),
    "aws_vpc_security_group_ingress_rule.alb_http": (
        "aws_vpc_security_group_ingress_rule"
    ),
    "aws_vpc_security_group_ingress_rule.ecs_from_alb": (
        "aws_vpc_security_group_ingress_rule"
    ),
}
ECS_TRANSITION_TYPES = {"aws_ecs_service", "aws_ecs_task_definition"}
TASK_DEFINITION_ADDRESS = "aws_ecs_task_definition.app"
RUNNER_INGRESS_BASE_ADDRESS = "aws_vpc_security_group_ingress_rule.alb_http"
UNKNOWN_TASK_ACTIONS = {("create",), ("update",)}


def managed_changes(plan: dict[str, Any]) -> list[dict[str, Any]]:
    """Return managed resource changes and reject unknown application types."""
    changes = [
        change
        for change in plan.get("resource_changes", [])
        if change.get("mode", "managed") == "managed"
    ]
    for change in changes:
        address = change.get("address", "")
        base_address = address.split("[", 1)[0]
        require(
            base_address in EXPECTED_RESOURCES,
            "unexpected application resource address",
        )
        require(
            change.get("type") == EXPECTED_RESOURCES[base_address],
            "resource address/type mismatch",
        )
    return changes


def active_changes(changes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Remove no-op and read-only entries from a plan change list."""
    return [
        change
        for change in changes
        if change.get("change", {}).get("actions", []) not in (["no-op"], ["read"])
    ]


def safe_counts(changes: list[dict[str, Any]]) -> tuple[int, int, int]:
    """Compute Terraform-style action counts without exposing addresses."""
    actions = [change.get("change", {}).get("actions", []) for change in changes]
    added = sum("create" in item for item in actions)
    changed = sum("update" in item for item in actions)
    destroyed = sum("delete" in item for item in actions)
    return added, changed, destroyed


def find_managed_change(plan: dict[str, Any], address: str) -> dict[str, Any]:
    """Return one exact managed resource change or fail closed."""
    matches = [
        change
        for change in plan.get("resource_changes", [])
        if change.get("mode", "managed") == "managed"
        and change.get("address") == address
    ]
    require(len(matches) == 1, f"expected exactly one change for {address}")
    return matches[0]


def configuration_references(plan: dict[str, Any], address: str, name: str) -> set[str]:
    """Return references for one exact Terraform configuration expression."""
    resources = (
        plan.get("configuration", {}).get("root_module", {}).get("resources", [])
    )
    matches = [resource for resource in resources if resource.get("address") == address]
    require(len(matches) == 1, f"expected exactly one configuration for {address}")
    expression = matches[0].get("expressions", {}).get(name)
    require(isinstance(expression, dict), f"missing {address}.{name} expression")
    references = expression.get("references")
    require(isinstance(references, list), f"missing {address}.{name} references")
    require(
        all(isinstance(reference, str) for reference in references),
        f"invalid {address}.{name} references",
    )
    return set(references)


def allow_unknown_bootstrap_container_definitions(
    plan: dict[str, Any], task: dict[str, Any], sha: str
) -> None:
    """Accept the observed first-create unknown only under exact invariants."""
    values = task.get("values", {})
    require(
        "container_definitions" not in values,
        "unknown container definitions must be omitted from planned values",
    )

    task_change = find_managed_change(plan, TASK_DEFINITION_ADDRESS)
    change = task_change.get("change", {})
    require(
        tuple(change.get("actions", [])) in UNKNOWN_TASK_ACTIONS,
        "unknown task definition has an unapproved change action",
    )
    require(
        "container_definitions" not in change.get("after", {}),
        "unknown container definitions must be omitted from change.after",
    )
    require(
        change.get("after_unknown", {}).get("container_definitions") is True,
        "container definitions are absent without an explicit Terraform unknown marker",
    )
    require(
        plan.get("variables", {}).get("image_tag", {}).get("value") == sha,
        "planned image_tag differs from the exact expected Git SHA",
    )

    references = configuration_references(
        plan, TASK_DEFINITION_ADDRESS, "container_definitions"
    )
    require(
        "aws_ecr_repository.app.repository_url" in references,
        "task definition image is not derived from the managed ECR repository URL",
    )
    require(
        "var.image_tag" in references,
        "task definition image is not derived from the required image_tag input",
    )


def validate_planned_application(
    plan: dict[str, Any], mode: str, sha: str, desired_count: int, cidr: str
) -> None:
    """Validate the planned ECS image/count, ECR protections, and runner CIDR."""
    service = find_one_resource(plan, "aws_ecs_service")
    require(
        service.get("values", {}).get("desired_count") == desired_count,
        "unexpected ECS desired count",
    )

    task = find_one_resource(plan, "aws_ecs_task_definition")
    raw_definitions = task.get("values", {}).get("container_definitions")
    if isinstance(raw_definitions, str):
        images = container_images(task)
        require(
            all(image.endswith(f":{sha}") for image in images),
            "task image is not the exact Git SHA",
        )
        require(
            all(":latest" not in image for image in images),
            "latest task image is forbidden",
        )
        require(
            all(":bootstrap" not in image for image in images),
            "bootstrap task image is forbidden",
        )
    else:
        require(
            mode == "bootstrap" and desired_count == 0,
            "container definitions must be concrete outside zero-task bootstrap",
        )
        allow_unknown_bootstrap_container_definitions(plan, task, sha)

    repository = find_one_resource(plan, "aws_ecr_repository")
    repository_values = repository.get("values", {})
    require(
        repository_values.get("image_tag_mutability") == "IMMUTABLE",
        "ECR must remain immutable",
    )
    require(
        repository_values.get("force_delete") is False,
        "ECR force_delete must remain false",
    )

    ingress = find_one_address(plan, "aws_vpc_security_group_ingress_rule.alb_http")
    require(
        ingress.get("values", {}).get("cidr_ipv4") == cidr,
        "runner CIDR changed unexpectedly",
    )


def validate_plan(
    plan: dict[str, Any], mode: str, sha: str | None = None, cidr: str | None = None
) -> tuple[int, int, int]:
    """Validate one lifecycle plan and return safe action counts."""
    changes = managed_changes(plan)
    active = active_changes(changes)

    if mode == "destroy":
        require(active, "destroy plan contains no managed-resource changes")
        require(
            all(
                change.get("change", {}).get("actions") == ["delete"]
                for change in active
            ),
            "destroy plan is not deletion-only",
        )
    else:
        require(sha is not None and cidr is not None, "SHA and CIDR are required")
        checked_sha = require_sha(sha)
        checked_cidr = require_ipv4_cidr(cidr)
        require(
            plan.get("variables", {}).get("image_tag", {}).get("value") == checked_sha,
            "planned image_tag differs from the exact expected Git SHA",
        )
        desired_count = 0 if mode in {"bootstrap", "scale-zero"} else 1
        validate_planned_application(
            plan, mode, checked_sha, desired_count, checked_cidr
        )

        if mode == "bootstrap":
            destructive = [
                change
                for change in active
                if "delete"
                in change.get(
                    "change",
                    {},
                ).get(
                    "actions",
                    [],
                )
            ]

            destructive_addresses = [
                change.get("address", "") for change in destructive
            ]

            require(
                len(destructive_addresses) == len(set(destructive_addresses)),
                "bootstrap plan contains duplicate destructive changes",
            )

            task_replacements = [
                change
                for change in destructive
                if change.get("address") == TASK_DEFINITION_ADDRESS
            ]

            runner_deletions = [
                change
                for change in destructive
                if change.get("address", "").split("[", 1)[0]
                == RUNNER_INGRESS_BASE_ADDRESS
            ]

            unexpected_destruction = [
                change
                for change in destructive
                if change not in task_replacements and change not in runner_deletions
            ]

            require(
                not unexpected_destruction,
                "bootstrap plan proposes unexpected destruction",
            )

            require(
                len(task_replacements) <= 1
                and all(
                    change.get("change", {}).get("actions") == ["delete", "create"]
                    for change in task_replacements
                ),
                "bootstrap task definition replacement is invalid",
            )

            require(
                len(runner_deletions) <= 1
                and all(
                    change.get("change", {}).get("actions") == ["delete"]
                    for change in runner_deletions
                ),
                "bootstrap runner ingress deletion is invalid",
            )

            if runner_deletions:
                runner_creations = [
                    change
                    for change in active
                    if change.get("address", "").split("[", 1)[0]
                    == RUNNER_INGRESS_BASE_ADDRESS
                    and change.get("change", {}).get("actions") == ["create"]
                ]

                require(
                    len(runner_creations) == 1,
                    "runner ingress deletion requires one replacement creation",
                )

                require(
                    runner_creations[0].get("address")
                    != runner_deletions[0].get("address"),
                    "runner ingress replacement addresses must differ",
                )
        else:
            require(
                all(change.get("type") in ECS_TRANSITION_TYPES for change in active),
                "ECS transition plan changes non-ECS infrastructure",
            )
            require(
                all(
                    change.get("change", {}).get("actions")
                    in (["update"], ["delete", "create"])
                    for change in active
                ),
                "ECS transition contains an unexpected action",
            )

    return safe_counts(active)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan-json", required=True)
    parser.add_argument(
        "--mode", required=True, choices=("bootstrap", "live", "scale-zero", "destroy")
    )
    parser.add_argument("--sha")
    parser.add_argument("--cidr")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        plan = load_json(args.plan_json)
        require(isinstance(plan, dict), "Terraform plan JSON must be an object")
        added, changed, destroyed = validate_plan(plan, args.mode, args.sha, args.cidr)
    except PolicyError as exc:
        print(f"Plan policy failed: {exc}", file=sys.stderr)
        return 1
    print(f"Plan policy passed: add={added} change={changed} destroy={destroyed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
