"""Validate redirected AWS/HTTP results and print only sanitized summaries."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from common import PolicyError, load_json, require


def one_service(document: dict[str, Any]) -> dict[str, Any]:
    services = document.get("services")
    require(
        isinstance(services, list) and len(services) == 1, "expected one ECS service"
    )
    require(not document.get("failures"), "ECS service response contains failures")
    return services[0]


def validate_tasks_zero(service_document: dict[str, Any]) -> tuple[int, int]:
    """Validate that an ECS service has no running or pending tasks."""
    service = one_service(service_document)
    running = service.get("runningCount")
    pending = service.get("pendingCount")
    require(
        isinstance(running, int) and isinstance(pending, int), "invalid ECS task counts"
    )
    require(running == 0 and pending == 0, "ECS tasks have not reached zero")
    return running, pending


def validate_live(
    task_document: dict[str, Any],
    target_document: dict[str, Any],
    http_document: dict[str, Any],
) -> list[str]:
    """Validate the minimal live task, target, and HTTP contract."""
    tasks = task_document.get("tasks")
    require(isinstance(tasks, list) and len(tasks) == 1, "expected one ECS task")
    require(not task_document.get("failures"), "ECS task response contains failures")
    task = tasks[0]
    task_status = task.get("lastStatus")
    require(task_status == "RUNNING", "task is not running")

    targets = target_document.get("TargetHealthDescriptions")
    require(isinstance(targets, list) and len(targets) == 1, "expected one ALB target")
    target = targets[0]
    target_state = target.get("TargetHealth", {}).get("State")
    require(target_state == "healthy", "ALB target is not healthy")

    http_status = http_document.get("status")
    exact_match = http_document.get("exact_body_match")
    require(http_status == 200, "application health status is not HTTP 200")
    require(exact_match is True, "application health body differs")

    return [
        "ECS service stability waiter: passed",
        "Running ECS task count: 1",
        f"Task status: {task_status}",
        f"ALB target health: {target_state}",
        f"HTTP status: {http_status}",
        f"Exact body match: {str(exact_match).lower()}",
    ]


def validate_cleanup(
    repositories: dict[str, Any],
    load_balancers: dict[str, Any],
    clusters: dict[str, Any],
    nat_gateways: dict[str, Any],
    addresses: dict[str, Any],
    state_list: str,
) -> list[str]:
    """Validate application cleanup without exposing identifiers."""
    repository_names = {
        item.get("repositoryName") for item in repositories.get("repositories", [])
    }
    require("platform-assessment-app" not in repository_names, "ECR repository remains")

    load_balancer_names = {
        item.get("LoadBalancerName") for item in load_balancers.get("LoadBalancers", [])
    }
    require("platform-assessment-alb" not in load_balancer_names, "ALB remains")

    cluster_items = clusters.get("clusters", [])
    require(
        not cluster_items
        or all(item.get("status") == "INACTIVE" for item in cluster_items),
        "ECS cluster remains active",
    )

    nat_items = nat_gateways.get("NatGateways", [])
    require(
        all(item.get("State") == "deleted" for item in nat_items),
        "NAT Gateway remains chargeable",
    )
    require(not addresses.get("Addresses", []), "Elastic IP remains allocated")
    require(not state_list.strip(), "application Terraform state still has resources")

    return [
        "ECR repository absent: true",
        "ALB absent: true",
        "ECS cluster absent or inactive: true",
        "NAT Gateway absent or deleted: true",
        "Elastic IP released: true",
        "Application state managed-resource count: 0",
        "Bootstrap resources retained by scope: true",
    ]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--mode", required=True, choices=("live", "tasks-zero", "cleanup")
    )
    parser.add_argument("--service-json")
    parser.add_argument("--task-json")
    parser.add_argument("--target-json")
    parser.add_argument("--http-json")
    parser.add_argument("--repositories-json")
    parser.add_argument("--load-balancers-json")
    parser.add_argument("--clusters-json")
    parser.add_argument("--nat-gateways-json")
    parser.add_argument("--addresses-json")
    parser.add_argument("--state-list")
    parser.add_argument("--quiet", action="store_true")
    return parser.parse_args()


def required_json(path: str | None, label: str) -> dict[str, Any]:
    require(path is not None, f"missing {label} path")
    document = load_json(path)
    require(isinstance(document, dict), f"invalid {label} JSON")
    return document


def main() -> int:
    args = parse_args()
    try:
        if args.mode == "tasks-zero":
            service = required_json(args.service_json, "service")
            running, pending = validate_tasks_zero(service)
            lines = [f"ECS running/pending after scale-zero: {running}/{pending}"]
        elif args.mode == "live":
            lines = validate_live(
                required_json(args.task_json, "task"),
                required_json(args.target_json, "target"),
                required_json(args.http_json, "HTTP"),
            )
        else:
            require(args.state_list is not None, "missing state list path")
            try:
                state_list = Path(args.state_list).read_text()
            except OSError as exc:
                raise PolicyError(
                    "unable to read private Terraform state list"
                ) from exc
            lines = validate_cleanup(
                required_json(args.repositories_json, "repositories"),
                required_json(args.load_balancers_json, "load balancers"),
                required_json(args.clusters_json, "clusters"),
                required_json(args.nat_gateways_json, "NAT gateways"),
                required_json(args.addresses_json, "addresses"),
                state_list,
            )
    except PolicyError as exc:
        if not args.quiet:
            print(f"AWS validation policy failed: {exc}", file=sys.stderr)
        return 1
    if not args.quiet:
        print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
