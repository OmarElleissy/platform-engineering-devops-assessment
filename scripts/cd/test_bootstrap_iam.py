"""Static regression tests for the Phase 3C bootstrap IAM boundaries."""

from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
IAM_PATH = ROOT / "bootstrap" / "iam.tf"
OIDC_PATH = ROOT / "bootstrap" / "oidc.tf"

ACTION_RE = re.compile(
    r'"((?:ec2|ecr|ecs|elasticloadbalancing|iam|logs|s3):[A-Z][A-Za-z0-9]+)"'
)
LOCAL_ARN_RE = re.compile(r"local\.[a-z0-9_]+_arn")

REQUIRED_TERRAFORM_ACTIONS = set(
    """
    ec2:AllocateAddress ec2:AssociateRouteTable ec2:AttachInternetGateway
    ec2:AuthorizeSecurityGroupEgress ec2:AuthorizeSecurityGroupIngress
    ec2:CreateInternetGateway ec2:CreateNatGateway ec2:CreateRoute
    ec2:CreateRouteTable ec2:CreateSecurityGroup ec2:CreateSubnet ec2:CreateTags
    ec2:CreateVpc ec2:DeleteInternetGateway ec2:DeleteNatGateway ec2:DeleteRoute
    ec2:DeleteRouteTable ec2:DeleteSecurityGroup ec2:DeleteSubnet ec2:DeleteTags
    ec2:DeleteVpc ec2:DescribeAddresses ec2:DescribeAddressesAttribute
    ec2:DescribeAvailabilityZones
    ec2:DescribeInternetGateways ec2:DescribeNatGateways ec2:DescribeNetworkAcls
    ec2:DescribeNetworkInterfaces ec2:DescribeRouteTables
    ec2:DescribeSecurityGroupRules ec2:DescribeSecurityGroups ec2:DescribeSubnets
    ec2:DescribeVpcAttribute ec2:DescribeVpcs ec2:DetachInternetGateway
    ec2:DisassociateRouteTable ec2:ModifySubnetAttribute ec2:ModifyVpcAttribute
    ec2:ReleaseAddress ec2:RevokeSecurityGroupEgress
    ec2:RevokeSecurityGroupIngress
    ecr:BatchCheckLayerAvailability ecr:BatchDeleteImage ecr:BatchGetImage
    ecr:CompleteLayerUpload ecr:CreateRepository ecr:DeleteRepository
    ecr:DescribeImages ecr:DescribeRepositories ecr:GetAuthorizationToken
    ecr:GetDownloadUrlForLayer ecr:InitiateLayerUpload ecr:ListImages
    ecr:ListTagsForResource ecr:PutImage ecr:PutImageScanningConfiguration
    ecr:PutImageTagMutability ecr:TagResource ecr:UntagResource
    ecr:UploadLayerPart
    ecs:CreateCluster ecs:CreateService ecs:DeleteCluster ecs:DeleteService
    ecs:DeregisterTaskDefinition ecs:DescribeClusters ecs:DescribeServices
    ecs:DescribeServiceDeployments
    ecs:DescribeTaskDefinition ecs:DescribeTasks ecs:ListClusters ecs:ListServices
    ecs:ListServiceDeployments ecs:ListTagsForResource ecs:ListTaskDefinitions 
    ecs:ListTasks
    ecs:RegisterTaskDefinition ecs:StopTask ecs:TagResource ecs:UntagResource
    ecs:UpdateService
    elasticloadbalancing:AddTags elasticloadbalancing:CreateListener
    elasticloadbalancing:CreateLoadBalancer elasticloadbalancing:CreateTargetGroup
    elasticloadbalancing:DeleteListener elasticloadbalancing:DeleteLoadBalancer
    elasticloadbalancing:DeleteTargetGroup
    elasticloadbalancing:DescribeAccountLimits
    elasticloadbalancing:DescribeCapacityReservation
    elasticloadbalancing:DescribeListenerAttributes
    elasticloadbalancing:DescribeListeners
    elasticloadbalancing:DescribeLoadBalancerAttributes
    elasticloadbalancing:DescribeLoadBalancers elasticloadbalancing:DescribeTags
    elasticloadbalancing:DescribeTargetGroupAttributes
    elasticloadbalancing:DescribeTargetGroups
    elasticloadbalancing:DescribeTargetHealth
    elasticloadbalancing:ModifyLoadBalancerAttributes
    elasticloadbalancing:ModifyTargetGroup
    elasticloadbalancing:ModifyTargetGroupAttributes
    elasticloadbalancing:RemoveTags
    iam:CreateRole iam:CreateServiceLinkedRole iam:DeleteRole
    iam:DeleteRolePolicy iam:GetRole iam:GetRolePolicy
    iam:ListAttachedRolePolicies iam:ListInstanceProfilesForRole
    iam:ListRolePolicies iam:ListRoleTags iam:PassRole iam:PutRolePolicy
    iam:TagRole iam:UntagRole iam:UpdateAssumeRolePolicy
    logs:CreateLogGroup logs:DeleteLogGroup logs:DescribeLogGroups
    logs:DescribeLogStreams logs:FilterLogEvents logs:GetLogEvents
    logs:ListTagsForResource logs:PutRetentionPolicy logs:TagResource
    logs:UntagResource
    s3:DeleteObject s3:GetBucketLocation s3:GetObject s3:ListBucket s3:PutObject
    """.split()
)

BROAD_REGIONAL_ACTIONS = {
    "ReadECSAccountMetadata": {
        "ecs:DescribeServiceDeployments",
        "ecs:DescribeTaskDefinition",
        "ecs:ListClusters",
        "ecs:ListServices",
        "ecs:ListTaskDefinitions",
    },
    "DescribeRegionalELBv2Resources": {
        "elasticloadbalancing:DescribeAccountLimits",
        "elasticloadbalancing:DescribeCapacityReservation",
        "elasticloadbalancing:DescribeListenerAttributes",
        "elasticloadbalancing:DescribeListeners",
        "elasticloadbalancing:DescribeLoadBalancerAttributes",
        "elasticloadbalancing:DescribeLoadBalancers",
        "elasticloadbalancing:DescribeTags",
        "elasticloadbalancing:DescribeTargetGroupAttributes",
        "elasticloadbalancing:DescribeTargetGroups",
        "elasticloadbalancing:DescribeTargetHealth",
    },
    "DescribeRegionalNetworkResources": {
        "ec2:DescribeAddresses",
        "ec2:DescribeAddressesAttribute",
        "ec2:DescribeAvailabilityZones",
        "ec2:DescribeInternetGateways",
        "ec2:DescribeNatGateways",
        "ec2:DescribeNetworkAcls",
        "ec2:DescribeNetworkInterfaces",
        "ec2:DescribeRouteTables",
        "ec2:DescribeSecurityGroupRules",
        "ec2:DescribeSecurityGroups",
        "ec2:DescribeSubnets",
        "ec2:DescribeVpcAttribute",
        "ec2:DescribeVpcs",
    },
    "DescribeRegionalLogGroups": {"logs:DescribeLogGroups"},
}


def statement_block(text: str, sid: str) -> str:
    """Extract one Terraform IAM statement block by SID."""
    marker = re.search(rf'^\s*sid\s*=\s*"{re.escape(sid)}"\s*$', text, re.MULTILINE)
    if marker is None:
        raise AssertionError(f"missing IAM statement {sid}")
    start = text.rfind("statement {", 0, marker.start())
    if start < 0:
        raise AssertionError(f"missing opening block for {sid}")

    depth = 0
    for index in range(start, len(text)):
        if text[index] == "{":
            depth += 1
        elif text[index] == "}":
            depth -= 1
            if depth == 0:
                return text[start : index + 1]
    raise AssertionError(f"unterminated IAM statement {sid}")


def actions(block: str) -> set[str]:
    """Return IAM actions from one Terraform statement block."""
    return set(ACTION_RE.findall(block)) - {
        "iam:AWSServiceName",
        "iam:PassedToService",
    }


def local_arns(block: str) -> set[str]:
    """Return local ARN expressions from one Terraform statement block."""
    return set(LOCAL_ARN_RE.findall(block))


class BootstrapIAMPolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.iam = IAM_PATH.read_text(encoding="utf-8")
        cls.oidc = OIDC_PATH.read_text(encoding="utf-8")

    def test_terraform_action_set_is_exact(self) -> None:
        policy_actions = actions(self.iam) - {"ec2:CreateAction"}
        self.assertEqual(policy_actions, REQUIRED_TERRAFORM_ACTIONS)

    def test_state_bucket_location_and_listing_are_separately_scoped(
        self,
    ) -> None:
        location = statement_block(self.iam, "ReadStateBucketLocation")
        self.assertEqual(actions(location), {"s3:GetBucketLocation"})
        self.assertIn(
            "resources = [aws_s3_bucket.terraform_state.arn]",
            location,
        )
        self.assertNotIn("s3:prefix", location)
        self.assertNotIn("condition {", location)

        listing = statement_block(self.iam, "ReadStateBucketMetadata")
        self.assertEqual(actions(listing), {"s3:ListBucket"})
        self.assertIn(
            "resources = [aws_s3_bucket.terraform_state.arn]",
            listing,
        )
        self.assertEqual(listing.count("condition {"), 1)
        self.assertIn('test     = "StringLike"', listing)
        self.assertIn('variable = "s3:prefix"', listing)
        self.assertIn("var.state_key,", listing)
        self.assertIn('"${var.state_key}.tflock",', listing)

    def test_network_creates_name_all_new_resource_types(self) -> None:
        block = statement_block(self.iam, "CreateTaggedNetworkResources")
        self.assertEqual(
            local_arns(block),
            {
                "local.elastic_ip_arn",
                "local.internet_gateway_arn",
                "local.nat_gateway_arn",
                "local.route_table_arn",
                "local.security_group_arn",
                "local.subnet_arn",
                "local.vpc_arn",
            },
        )
        self.assertIn('variable = "aws:RequestTag/Project"', block)
        self.assertIn('variable = "aws:RequestedRegion"', block)

    def test_security_group_rule_tagging_is_limited_to_rule_creation(
        self,
    ) -> None:
        block = statement_block(
            self.iam,
            "TagNewSecurityGroupRules",
        )

        self.assertEqual(
            actions(block),
            {
                "ec2:CreateAction",
                "ec2:CreateTags",
            },
        )
        self.assertIn(
            'actions = ["ec2:CreateTags"]',
            block,
        )
        self.assertEqual(
            local_arns(block),
            {"local.security_group_rule_arn"},
        )
        self.assertIn(
            'variable = "aws:RequestedRegion"',
            block,
        )
        self.assertIn(
            'variable = "aws:RequestTag/Project"',
            block,
        )
        self.assertIn(
            'variable = "ec2:CreateAction"',
            block,
        )
        self.assertIn(
            '"AuthorizeSecurityGroupEgress"',
            block,
        )
        self.assertIn(
            '"AuthorizeSecurityGroupIngress"',
            block,
        )

    def test_vpc_dependent_creates_require_the_tagged_vpc(self) -> None:
        block = statement_block(self.iam, "UseTaggedVpcForNetworkCreation")
        self.assertEqual(
            actions(block),
            {
                "ec2:CreateNatGateway",
                "ec2:CreateRouteTable",
                "ec2:CreateSecurityGroup",
                "ec2:CreateSubnet",
            },
        )
        self.assertEqual(local_arns(block), {"local.vpc_arn"})
        self.assertIn('variable = "aws:ResourceTag/Project"', block)
        self.assertIn('variable = "aws:RequestedRegion"', block)

    def test_nat_gateway_requires_tagged_eip_and_subnet(self) -> None:
        block = statement_block(self.iam, "UseTaggedNatGatewayDependencies")
        self.assertEqual(actions(block), {"ec2:CreateNatGateway"})
        self.assertEqual(
            local_arns(block), {"local.elastic_ip_arn", "local.subnet_arn"}
        )
        self.assertIn('variable = "aws:ResourceTag/Project"', block)
        self.assertIn('variable = "aws:RequestedRegion"', block)

    def test_broad_regional_reads_are_exact_and_region_limited(self) -> None:
        for sid, expected_actions in BROAD_REGIONAL_ACTIONS.items():
            with self.subTest(sid=sid):
                block = statement_block(self.iam, sid)
                self.assertEqual(actions(block), expected_actions)
                self.assertIn('resources = ["*"]', block)
                self.assertIn('variable = "aws:RequestedRegion"', block)

    def test_service_deployment_describe_is_broad_and_list_remains_scoped(
        self,
    ) -> None:
        broad = statement_block(self.iam, "ReadECSAccountMetadata")
        self.assertIn('"ecs:DescribeServiceDeployments"', broad)
        self.assertIn('resources = ["*"]', broad)
        self.assertIn('variable = "aws:RequestedRegion"', broad)
        self.assertIn("values   = [var.aws_region]", broad)

        scoped = statement_block(self.iam, "ManageNamedECSResources")
        self.assertNotIn('"ecs:DescribeServiceDeployments"', scoped)
        self.assertIn('"ecs:ListServiceDeployments"', scoped)

    def test_list_tasks_is_wildcard_for_the_exact_cluster_and_region(
        self,
    ) -> None:
        scoped = statement_block(self.iam, "ManageNamedECSResources")
        self.assertNotIn('"ecs:ListTasks"', scoped)

        block = statement_block(self.iam, "ListTasksInExactCluster")
        self.assertEqual(actions(block), {"ecs:ListTasks"})
        self.assertIn('resources = ["*"]', block)
        self.assertEqual(block.count("condition {"), 2)
        self.assertIn('test     = "StringEquals"', block)
        self.assertIn('variable = "aws:RequestedRegion"', block)
        self.assertIn("values   = [var.aws_region]", block)
        self.assertIn('test     = "ArnEquals"', block)
        self.assertIn('variable = "ecs:cluster"', block)
        self.assertIn("values   = [local.ecs_cluster_arn]", block)
        self.assertEqual(local_arns(block), {"local.ecs_cluster_arn"})

    def test_task_definition_deregistration_is_wildcard_and_region_limited(
        self,
    ) -> None:
        scoped = statement_block(self.iam, "ManageNamedECSResources")
        self.assertNotIn('"ecs:DeregisterTaskDefinition"', scoped)

        block = statement_block(self.iam, "DeregisterTaskDefinition")
        self.assertEqual(actions(block), {"ecs:DeregisterTaskDefinition"})
        self.assertIn('resources = ["*"]', block)
        self.assertEqual(block.count("condition {"), 1)
        self.assertIn('test     = "StringEquals"', block)
        self.assertIn('variable = "aws:RequestedRegion"', block)
        self.assertIn("values   = [var.aws_region]", block)

    def test_pass_role_remains_exact_and_service_limited(self) -> None:
        block = statement_block(self.iam, "PassExactECSExecutionRole")
        self.assertEqual(actions(block), {"iam:PassRole"})
        self.assertEqual(local_arns(block), {"local.ecs_execution_role_arn"})
        self.assertIn('variable = "iam:PassedToService"', block)
        self.assertIn('values   = ["ecs-tasks.amazonaws.com"]', block)

    def test_lifecycle_role_cannot_modify_itself(self) -> None:
        block = statement_block(self.iam, "ManageExactECSExecutionRole")
        self.assertEqual(local_arns(block), {"local.ecs_execution_role_arn"})
        self.assertNotIn("cd_lifecycle", block)

    def test_application_state_deletion_remains_prohibited(self) -> None:
        state = statement_block(self.iam, "ReadWriteApplicationState")
        lock = statement_block(self.iam, "ManageNativeStateLock")
        self.assertNotIn('"s3:DeleteObject"', state)
        self.assertIn('"s3:DeleteObject"', lock)

    def test_oidc_subject_is_exact_without_wildcards(self) -> None:
        block = statement_block(self.oidc, "GitHubActionsLifecycleWorkflows")
        self.assertIn('variable = "${local.github_oidc_namespace}:sub"', block)
        self.assertIn("values   = [var.github_oidc_subject]", block)
        self.assertNotIn("StringLike", block)
        self.assertNotIn("*", block)

    def test_no_aws_managed_administrative_policy_is_attached(self) -> None:
        terraform = "\n".join(
            path.read_text(encoding="utf-8")
            for path in sorted((ROOT / "bootstrap").glob("*.tf"))
        )
        self.assertNotIn('resource "aws_iam_role_policy_attachment"', terraform)
        self.assertNotIn('resource "aws_iam_policy_attachment"', terraform)
        self.assertNotRegex(terraform, r"AdministratorAccess|PowerUserAccess")


if __name__ == "__main__":
    unittest.main()
