"""Focused unit tests for fail-closed Phase 3C policy functions."""

from __future__ import annotations

import json
import unittest

from aws_policy import validate_live
from common import PolicyError
from ecr_policy import find_tag, validated_inventory
from sanitize_apply import extract_summary
from terraform_plan_policy import validate_plan

SHA = "0123456789abcdef0123456789abcdef01234567"
CIDR = "192.0.2.10/32"


def plan_fixture(actions: list[str], desired_count: int) -> dict:
    """Return the smallest representative application plan document."""
    return {
        "planned_values": {
            "root_module": {
                "resources": [
                    {
                        "address": "aws_ecs_service.app",
                        "type": "aws_ecs_service",
                        "values": {"desired_count": desired_count},
                    },
                    {
                        "address": "aws_ecs_task_definition.app",
                        "type": "aws_ecs_task_definition",
                        "values": {
                            "container_definitions": json.dumps(
                                [{"image": f"example.invalid/app:{SHA}"}]
                            )
                        },
                    },
                    {
                        "address": "aws_ecr_repository.app",
                        "type": "aws_ecr_repository",
                        "values": {
                            "image_tag_mutability": "IMMUTABLE",
                            "force_delete": False,
                        },
                    },
                    {
                        "address": (
                            'aws_vpc_security_group_ingress_rule.alb_http["runner"]'
                        ),
                        "type": "aws_vpc_security_group_ingress_rule",
                        "values": {"cidr_ipv4": CIDR},
                    },
                    {
                        "address": "aws_vpc_security_group_ingress_rule.ecs_from_alb",
                        "type": "aws_vpc_security_group_ingress_rule",
                        "values": {"referenced_security_group_id": "sg-private"},
                    },
                ]
            }
        },
        "resource_changes": [
            {
                "address": "aws_ecs_service.app",
                "mode": "managed",
                "type": "aws_ecs_service",
                "change": {"actions": actions},
            }
        ],
    }


class TerraformPlanPolicyTests(unittest.TestCase):
    def test_live_service_update_passes(self) -> None:
        self.assertEqual(
            validate_plan(plan_fixture(["update"], 1), "live", SHA, CIDR), (0, 1, 0)
        )

    def test_bootstrap_rejects_deletion(self) -> None:
        with self.assertRaises(PolicyError):
            validate_plan(plan_fixture(["delete"], 0), "bootstrap", SHA, CIDR)

    def test_short_sha_is_rejected(self) -> None:
        with self.assertRaises(PolicyError):
            validate_plan(plan_fixture(["update"], 1), "live", "0123456", CIDR)

    def test_unapproved_resource_address_is_rejected(self) -> None:
        plan = plan_fixture(["update"], 1)
        plan["resource_changes"][0]["address"] = "aws_ecs_service.unrelated"
        with self.assertRaises(PolicyError):
            validate_plan(plan, "live", SHA, CIDR)

    def test_live_noop_is_restartable_when_values_are_exact(self) -> None:
        self.assertEqual(
            validate_plan(plan_fixture(["no-op"], 1), "live", SHA, CIDR), (0, 0, 0)
        )


class ECRPolicyTests(unittest.TestCase):
    def test_find_exact_tag(self) -> None:
        digest = "sha256:" + "a" * 64
        document = {"imageDetails": [{"imageDigest": digest, "imageTags": [SHA]}]}
        self.assertEqual(find_tag(document, SHA), digest)

    def test_inventory_rejects_untagged_image(self) -> None:
        document = {"imageDetails": [{"imageDigest": "sha256:" + "a" * 64}]}
        with self.assertRaises(PolicyError):
            validated_inventory(document)


class SanitizationTests(unittest.TestCase):
    def test_apply_summary_extracts_only_counts(self) -> None:
        raw = (
            "private details\n"
            "Apply complete! Resources: 2 added, 1 changed, 0 destroyed.\n"
        )
        self.assertEqual(extract_summary(raw), (2, 1, 0))


class AWSLivePolicyTests(unittest.TestCase):
    def test_live_summary_contains_only_safe_fields(self) -> None:
        service = {
            "services": [
                {
                    "status": "ACTIVE",
                    "desiredCount": 1,
                    "runningCount": 1,
                    "pendingCount": 0,
                    "deployments": [{"status": "PRIMARY", "rolloutState": "COMPLETED"}],
                }
            ],
            "failures": [],
        }
        tasks = {
            "tasks": [
                {
                    "launchType": "FARGATE",
                    "platformVersion": "1.4.0",
                    "lastStatus": "RUNNING",
                    "healthStatus": "HEALTHY",
                }
            ],
            "failures": [],
        }
        targets = {
            "TargetHealthDescriptions": [
                {"Target": {"Port": 8080}, "TargetHealth": {"State": "healthy"}}
            ]
        }
        http = {
            "status": 200,
            "exact_body_match": True,
            "five_request_success_count": 5,
        }
        logs = {
            "events": [
                {"message": "Application startup complete"},
                {"message": 'GET /health HTTP/1.1" 200'},
            ]
        }
        lines = validate_live(service, tasks, targets, http, logs)
        self.assertIn("ECS desired/running/pending: 1/1/0", lines)
        self.assertIn("CloudWatch log-delivery count: 2", lines)


if __name__ == "__main__":
    unittest.main()
