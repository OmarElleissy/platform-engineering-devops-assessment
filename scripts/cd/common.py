"""Shared fail-closed helpers for Phase 3C workflow policy scripts."""

from __future__ import annotations

import ipaddress
import json
import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any

SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")
DIGEST_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")


class PolicyError(ValueError):
    """Raised when private workflow input violates an expected policy."""


def require(condition: bool, message: str) -> None:
    """Raise a concise policy error when a condition is false."""
    if not condition:
        raise PolicyError(message)


def load_json(path: str | Path) -> Any:
    """Load JSON without ever printing its private contents."""
    try:
        return json.loads(Path(path).read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise PolicyError(
            f"unable to read valid private JSON: {Path(path).name}"
        ) from exc


def require_sha(value: str, label: str = "Git SHA") -> str:
    """Require an immutable full lowercase Git SHA."""
    require(
        bool(SHA_PATTERN.fullmatch(value)),
        f"{label} must be 40 lowercase hex characters",
    )
    return value


def require_digest(value: str) -> str:
    """Require a full sha256 container digest."""
    require(bool(DIGEST_PATTERN.fullmatch(value)), "invalid container image digest")
    return value


def require_ipv4_cidr(value: str) -> str:
    """Require exactly one host IPv4 CIDR and forbid a world-open source."""
    try:
        network = ipaddress.ip_network(value, strict=False)
    except ValueError as exc:
        raise PolicyError("allowed HTTP source is not a valid CIDR") from exc
    require(network.version == 4, "allowed HTTP source must be IPv4")
    require(network.prefixlen == 32, "allowed HTTP source must be a single-host /32")
    require(
        value == f"{network.network_address}/32", "allowed HTTP CIDR is not canonical"
    )
    require(value != "0.0.0.0/0", "world-open HTTP ingress is forbidden")
    return value


def iter_resources(module: dict[str, Any] | None) -> Iterator[dict[str, Any]]:
    """Yield Terraform resources recursively from a values module."""
    if not module:
        return
    yield from module.get("resources", [])
    for child in module.get("child_modules", []):
        yield from iter_resources(child)


def resources_by_address(document: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Index current or planned Terraform resources by address."""
    values = document.get("planned_values") or document.get("values") or {}
    root = values.get("root_module")
    return {resource["address"]: resource for resource in iter_resources(root)}


def find_one_address(document: dict[str, Any], address_prefix: str) -> dict[str, Any]:
    """Return the single resource whose address is exact or indexed by prefix."""
    matches = [
        resource
        for address, resource in resources_by_address(document).items()
        if address == address_prefix or address.startswith(f"{address_prefix}[")
    ]
    require(len(matches) == 1, f"expected exactly one {address_prefix} resource")
    return matches[0]


def find_one_resource(document: dict[str, Any], resource_type: str) -> dict[str, Any]:
    """Return the single resource of a type or fail closed."""
    matches = [
        resource
        for resource in resources_by_address(document).values()
        if resource.get("type") == resource_type
    ]
    require(len(matches) == 1, f"expected exactly one {resource_type} resource")
    return matches[0]


def container_images(task_definition: dict[str, Any]) -> list[str]:
    """Extract container images from an ECS task-definition resource."""
    raw = task_definition.get("values", {}).get("container_definitions")
    require(isinstance(raw, str), "task definition has no container definitions")
    try:
        definitions = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise PolicyError("task container definitions are invalid JSON") from exc
    require(isinstance(definitions, list) and definitions, "task has no containers")
    images = [item.get("image") for item in definitions]
    require(all(isinstance(image, str) for image in images), "task image is missing")
    return images


def mask_value(value: str) -> None:
    """Register an identifier with the GitHub log masker before other output."""
    require("\n" not in value and "\r" not in value, "masked value contains a newline")
    print(f"::add-mask::{value}")


def append_github_values(path: str | Path, values: dict[str, str]) -> None:
    """Append validated single-line values to a GitHub environment/output file."""
    destination = Path(path)
    with destination.open("a", encoding="utf-8") as stream:
        for name, value in values.items():
            require(re.fullmatch(r"[A-Z][A-Z0-9_]*", name) is not None, "invalid key")
            require("\n" not in value and "\r" not in value, "value contains a newline")
            stream.write(f"{name}={value}\n")
