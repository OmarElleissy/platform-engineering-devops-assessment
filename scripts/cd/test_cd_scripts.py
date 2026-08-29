"""Focused unit tests for fail-closed Phase 3C policy functions."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from aws_policy import validate_live
from common import PolicyError
from ecr_policy import find_tag, validated_inventory, write_batches
from sanitize_apply import extract_summary
from terraform_plan_policy import validate_plan

SHA = "0123456789abcdef0123456789abcdef01234567"
CIDR = "192.0.2.10/32"


def plan_fixture(
    actions: list[str],
    desired_count: int,
    *,
    image: str | None = None,
    image_tag: str = SHA,
    unknown_definitions: bool = False,
    unknown_marker: bool = True,
    task_actions: list[str] | None = None,
) -> dict:
    """Return the smallest representative application plan document."""
    task_values = {}
    if not unknown_definitions:
        task_values["container_definitions"] = json.dumps(
            [{"image": image or f"example.invalid/app:{SHA}"}]
        )

    resource_changes = [
        {
            "address": "aws_ecs_service.app",
            "mode": "managed",
            "type": "aws_ecs_service",
            "change": {"actions": actions},
        }
    ]
    if unknown_definitions:
        task_change = {
            "actions": task_actions or ["create"],
            "after": {},
            "after_unknown": {},
        }
        if unknown_marker:
            task_change["after_unknown"]["container_definitions"] = True
        resource_changes.append(
            {
                "address": "aws_ecs_task_definition.app",
                "mode": "managed",
                "type": "aws_ecs_task_definition",
                "change": task_change,
            }
        )

    return {
        "variables": {"image_tag": {"value": image_tag}},
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
                        "values": task_values,
                    },
                    {
                        "address": "aws_ecr_repository.app",
                        "type": "aws_ecr_repository",
                        "values": {
                            "image_tag_mutability": "IMMUTABLE",
                            "force_delete": True,
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
        "resource_changes": resource_changes,
        "configuration": {
            "root_module": {
                "resources": [
                    {
                        "address": "aws_ecs_task_definition.app",
                        "expressions": {
                            "container_definitions": {
                                "references": [
                                    "aws_ecr_repository.app.repository_url",
                                    "var.image_tag",
                                ]
                            }
                        },
                    }
                ]
            }
        },
    }


class TerraformPlanPolicyTests(unittest.TestCase):
    def test_live_service_update_passes(self) -> None:
        self.assertEqual(
            validate_plan(plan_fixture(["update"], 1), "live", SHA, CIDR), (0, 1, 0)
        )

    def test_bootstrap_accepts_task_definition_replacement(
        self,
    ) -> None:
        plan = plan_fixture(
            ["update"],
            0,
        )
        plan["resource_changes"].append(
            {
                "address": "aws_ecs_task_definition.app",
                "mode": "managed",
                "type": "aws_ecs_task_definition",
                "change": {
                    "actions": [
                        "delete",
                        "create",
                    ],
                    "after": {},
                    "after_unknown": {},
                },
            }
        )

        self.assertEqual(
            validate_plan(
                plan,
                "bootstrap",
                SHA,
                CIDR,
            ),
            (1, 1, 1),
        )

    def test_bootstrap_accepts_expected_redeploy_replacements(
        self,
    ) -> None:
        plan = plan_fixture(
            ["update"],
            0,
        )

        plan["resource_changes"].extend(
            [
                {
                    "address": "aws_ecs_task_definition.app",
                    "mode": "managed",
                    "type": "aws_ecs_task_definition",
                    "change": {
                        "actions": [
                            "delete",
                            "create",
                        ],
                        "after": {},
                        "after_unknown": {},
                    },
                },
                {
                    "address": (
                        "aws_vpc_security_group_ingress_rule."
                        'alb_http["203.0.113.10/32"]'
                    ),
                    "mode": "managed",
                    "type": ("aws_vpc_security_group_ingress_rule"),
                    "change": {
                        "actions": ["create"],
                        "after": {},
                        "after_unknown": {},
                    },
                },
                {
                    "address": (
                        "aws_vpc_security_group_ingress_rule."
                        'alb_http["198.51.100.10/32"]'
                    ),
                    "mode": "managed",
                    "type": ("aws_vpc_security_group_ingress_rule"),
                    "change": {
                        "actions": ["delete"],
                        "after": None,
                        "after_unknown": {},
                    },
                },
            ]
        )

        self.assertEqual(
            validate_plan(
                plan,
                "bootstrap",
                SHA,
                CIDR,
            ),
            (2, 1, 2),
        )

    def test_bootstrap_rejects_runner_deletion_without_creation(
        self,
    ) -> None:
        plan = plan_fixture(
            ["update"],
            0,
        )

        plan["resource_changes"].append(
            {
                "address": (
                    'aws_vpc_security_group_ingress_rule.alb_http["198.51.100.10/32"]'
                ),
                "mode": "managed",
                "type": ("aws_vpc_security_group_ingress_rule"),
                "change": {
                    "actions": ["delete"],
                    "after": None,
                    "after_unknown": {},
                },
            }
        )

        with self.assertRaises(PolicyError):
            validate_plan(
                plan,
                "bootstrap",
                SHA,
                CIDR,
            )

    def test_bootstrap_rejects_other_resource_replacement(
        self,
    ) -> None:
        plan = plan_fixture(
            [
                "delete",
                "create",
            ],
            0,
        )

        with self.assertRaises(PolicyError):
            validate_plan(
                plan,
                "bootstrap",
                SHA,
                CIDR,
            )

    def test_bootstrap_rejects_task_definition_delete_only(
        self,
    ) -> None:
        plan = plan_fixture(
            ["update"],
            0,
        )
        plan["resource_changes"].append(
            {
                "address": "aws_ecs_task_definition.app",
                "mode": "managed",
                "type": "aws_ecs_task_definition",
                "change": {
                    "actions": ["delete"],
                    "after": None,
                    "after_unknown": {},
                },
            }
        )

        with self.assertRaises(PolicyError):
            validate_plan(
                plan,
                "bootstrap",
                SHA,
                CIDR,
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

    def test_bootstrap_accepts_explicitly_unknown_container_definitions(self) -> None:
        plan = plan_fixture(["create"], 0, unknown_definitions=True)
        self.assertEqual(validate_plan(plan, "bootstrap", SHA, CIDR), (2, 0, 0))

    def test_bootstrap_rejects_missing_definitions_without_unknown_marker(self) -> None:
        plan = plan_fixture(
            ["create"], 0, unknown_definitions=True, unknown_marker=False
        )
        with self.assertRaises(PolicyError):
            validate_plan(plan, "bootstrap", SHA, CIDR)

    def test_bootstrap_rejects_unknown_definitions_with_desired_count_one(
        self,
    ) -> None:
        plan = plan_fixture(["create"], 1, unknown_definitions=True)
        with self.assertRaises(PolicyError):
            validate_plan(plan, "bootstrap", SHA, CIDR)

    def test_bootstrap_rejects_unknown_definitions_with_unexpected_tag(self) -> None:
        other_sha = "f" * 40
        plan = plan_fixture(
            ["create"], 0, image_tag=other_sha, unknown_definitions=True
        )
        with self.assertRaises(PolicyError):
            validate_plan(plan, "bootstrap", SHA, CIDR)

    def test_bootstrap_rejects_unknown_definitions_without_ecr_reference(
        self,
    ) -> None:
        plan = plan_fixture(["create"], 0, unknown_definitions=True)
        references = plan["configuration"]["root_module"]["resources"][0][
            "expressions"
        ]["container_definitions"]["references"]
        references.remove("aws_ecr_repository.app.repository_url")
        with self.assertRaises(PolicyError):
            validate_plan(plan, "bootstrap", SHA, CIDR)

    def test_live_rejects_unknown_container_definitions(self) -> None:
        plan = plan_fixture(
            ["update"], 1, unknown_definitions=True, task_actions=["update"]
        )
        with self.assertRaises(PolicyError):
            validate_plan(plan, "live", SHA, CIDR)

    def test_live_accepts_concrete_exact_sha_image(self) -> None:
        plan = plan_fixture(["update"], 1, image=f"example.invalid/app:{SHA}")
        self.assertEqual(validate_plan(plan, "live", SHA, CIDR), (0, 1, 0))

    def test_live_rejects_mutable_or_unexpected_image_tags(self) -> None:
        rejected_images = [
            "example.invalid/app:latest",
            "example.invalid/app:bootstrap",
            "example.invalid/app:0123456",
            f"example.invalid/app:{'f' * 40}",
            "example.invalid/app:feature-branch",
        ]
        for image in rejected_images:
            with self.subTest(image=image), self.assertRaises(PolicyError):
                validate_plan(
                    plan_fixture(["update"], 1, image=image), "live", SHA, CIDR
                )

    def test_live_rejects_disabled_force_delete(self) -> None:
        plan = plan_fixture(["update"], 1)
        repository = plan["planned_values"]["root_module"]["resources"][2]
        repository["values"]["force_delete"] = False
        with self.assertRaises(PolicyError):
            validate_plan(plan, "live", SHA, CIDR)

    def test_destroy_accepts_allowlisted_deletions_only(self) -> None:
        plan = {
            "resource_changes": [
                {
                    "address": "aws_ecr_repository.app",
                    "mode": "managed",
                    "type": "aws_ecr_repository",
                    "change": {"actions": ["delete"]},
                }
            ]
        }
        self.assertEqual(validate_plan(plan, "destroy"), (0, 0, 1))

    def test_destroy_rejects_non_deletion_or_unallowlisted_resource(self) -> None:
        invalid_changes = [
            {
                "address": "aws_ecr_repository.app",
                "mode": "managed",
                "type": "aws_ecr_repository",
                "change": {"actions": ["update"]},
            },
            {
                "address": "aws_s3_bucket.unrelated",
                "mode": "managed",
                "type": "aws_s3_bucket",
                "change": {"actions": ["delete"]},
            },
        ]
        for change in invalid_changes:
            with (
                self.subTest(address=change["address"]),
                self.assertRaises(PolicyError),
            ):
                validate_plan({"resource_changes": [change]}, "destroy")


class ECRPolicyTests(unittest.TestCase):
    def test_find_exact_tag(self) -> None:
        digest = "sha256:" + "a" * 64
        document = {"imageDetails": [{"imageDigest": digest, "imageTags": [SHA]}]}
        self.assertEqual(find_tag(document, SHA), digest)

    def test_inventory_rejects_untagged_image(self) -> None:
        document = {"imageDetails": [{"imageDigest": "sha256:" + "a" * 64}]}
        with self.assertRaises(PolicyError):
            validated_inventory(document)

    def test_write_batches_creates_raw_image_id_lists(self) -> None:
        digests = [f"sha256:{index:064x}" for index in range(101)]
        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual(write_batches(digests, directory), 2)
            first = json.loads((Path(directory) / "batch-0001.json").read_text())
            second = json.loads((Path(directory) / "batch-0002.json").read_text())

        self.assertIsInstance(first, list)
        self.assertIsInstance(second, list)
        self.assertEqual(len(first), 100)
        self.assertEqual(second, [{"imageDigest": digests[100]}])
        self.assertNotIsInstance(first, dict)


class SanitizationTests(unittest.TestCase):
    def test_apply_summary_extracts_only_counts(self) -> None:
        raw = (
            "private details\n"
            "Apply complete! Resources: 2 added, 1 changed, 0 destroyed.\n"
        )
        self.assertEqual(extract_summary(raw), (2, 1, 0))


class AWSLivePolicyTests(unittest.TestCase):
    def test_live_summary_contains_only_safe_fields(self) -> None:
        tasks = {
            "tasks": [
                {
                    "launchType": "FARGATE",
                    "platformVersion": "1.4.0",
                    "lastStatus": "RUNNING",
                    "healthStatus": "UNKNOWN",
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
        }
        lines = validate_live(tasks, targets, http)
        self.assertIn("ECS service stability waiter: passed", lines)
        self.assertIn("Running ECS task count: 1", lines)
        self.assertIn("Task status: RUNNING", lines)
        self.assertNotIn("Task health: UNKNOWN", lines)

    def test_live_gate_rejects_each_failed_outcome(self) -> None:
        valid_task = {"tasks": [{"lastStatus": "RUNNING"}], "failures": []}
        valid_target = {
            "TargetHealthDescriptions": [{"TargetHealth": {"State": "healthy"}}]
        }
        valid_http = {"status": 200, "exact_body_match": True}
        invalid_inputs = [
            ({"tasks": [], "failures": []}, valid_target, valid_http),
            (
                {"tasks": [{"lastStatus": "PENDING"}], "failures": []},
                valid_target,
                valid_http,
            ),
            (
                valid_task,
                {"TargetHealthDescriptions": [{"TargetHealth": {"State": "initial"}}]},
                valid_http,
            ),
            (valid_task, valid_target, {"status": 503, "exact_body_match": True}),
            (valid_task, valid_target, {"status": 200, "exact_body_match": False}),
        ]
        for task, target, http in invalid_inputs:
            with (
                self.subTest(task=task, target=target, http=http),
                self.assertRaises(PolicyError),
            ):
                validate_live(task, target, http)


if __name__ == "__main__":
    unittest.main()
