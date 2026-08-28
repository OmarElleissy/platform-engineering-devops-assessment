data "aws_caller_identity" "current" {}
data "aws_partition" "current" {}

locals {
  account_id = data.aws_caller_identity.current.account_id
  partition  = data.aws_partition.current.partition

  ecr_repository_arn = "arn:${local.partition}:ecr:${var.aws_region}:${local.account_id}:repository/${local.ecr_repository_name}"
  ecs_cluster_arn    = "arn:${local.partition}:ecs:${var.aws_region}:${local.account_id}:cluster/${local.ecs_cluster_name}"
  ecs_service_arn    = "arn:${local.partition}:ecs:${var.aws_region}:${local.account_id}:service/${local.ecs_cluster_name}/${local.ecs_service_name}"
  ecs_task_arn       = "arn:${local.partition}:ecs:${var.aws_region}:${local.account_id}:task/${local.ecs_cluster_name}/*"
  ecs_task_def_arn   = "arn:${local.partition}:ecs:${var.aws_region}:${local.account_id}:task-definition/${local.ecs_task_family}:*"
  ecs_execution_role_arn = format(
    "arn:%s:iam::%s:role/%s",
    local.partition,
    local.account_id,
    local.ecs_execution_role_name,
  )
  log_group_arn = "arn:${local.partition}:logs:${var.aws_region}:${local.account_id}:log-group:${local.log_group_name}"

  elastic_ip_arn          = "arn:${local.partition}:ec2:${var.aws_region}:${local.account_id}:elastic-ip/*"
  internet_gateway_arn    = "arn:${local.partition}:ec2:${var.aws_region}:${local.account_id}:internet-gateway/*"
  nat_gateway_arn         = "arn:${local.partition}:ec2:${var.aws_region}:${local.account_id}:natgateway/*"
  route_table_arn         = "arn:${local.partition}:ec2:${var.aws_region}:${local.account_id}:route-table/*"
  security_group_arn      = "arn:${local.partition}:ec2:${var.aws_region}:${local.account_id}:security-group/*"
  security_group_rule_arn = "arn:${local.partition}:ec2:${var.aws_region}:${local.account_id}:security-group-rule/*"
  subnet_arn              = "arn:${local.partition}:ec2:${var.aws_region}:${local.account_id}:subnet/*"
  vpc_arn                 = "arn:${local.partition}:ec2:${var.aws_region}:${local.account_id}:vpc/*"

  load_balancer_arn = "arn:${local.partition}:elasticloadbalancing:${var.aws_region}:${local.account_id}:loadbalancer/app/${local.application_name_prefix}-alb/*"
  target_group_arn  = "arn:${local.partition}:elasticloadbalancing:${var.aws_region}:${local.account_id}:targetgroup/${local.application_name_prefix}-tg/*"
  listener_arn      = "arn:${local.partition}:elasticloadbalancing:${var.aws_region}:${local.account_id}:listener/app/${local.application_name_prefix}-alb/*/*"
}

data "aws_iam_policy_document" "cd_lifecycle" {
  statement {
    sid    = "ReadStateBucketMetadata"
    effect = "Allow"
    actions = [
      "s3:GetBucketLocation",
      "s3:ListBucket",
    ]
    resources = [aws_s3_bucket.terraform_state.arn]

    condition {
      test     = "StringLike"
      variable = "s3:prefix"
      values = [
        var.state_key,
        "${var.state_key}.tflock",
      ]
    }
  }

  statement {
    sid    = "ReadWriteApplicationState"
    effect = "Allow"
    actions = [
      "s3:GetObject",
      "s3:PutObject",
    ]
    resources = ["${aws_s3_bucket.terraform_state.arn}/${var.state_key}"]
  }

  statement {
    sid    = "ManageNativeStateLock"
    effect = "Allow"
    actions = [
      "s3:DeleteObject",
      "s3:GetObject",
      "s3:PutObject",
    ]
    resources = ["${aws_s3_bucket.terraform_state.arn}/${var.state_key}.tflock"]
  }

  statement {
    sid       = "AuthenticateToECR"
    effect    = "Allow"
    actions   = ["ecr:GetAuthorizationToken"]
    resources = ["*"]

    condition {
      test     = "StringEquals"
      variable = "aws:RequestedRegion"
      values   = [var.aws_region]
    }
  }

  statement {
    sid    = "ManageAssessmentECRRepository"
    effect = "Allow"
    actions = [
      "ecr:BatchCheckLayerAvailability",
      "ecr:BatchDeleteImage",
      "ecr:BatchGetImage",
      "ecr:CompleteLayerUpload",
      "ecr:CreateRepository",
      "ecr:DeleteRepository",
      "ecr:DescribeImages",
      "ecr:DescribeRepositories",
      "ecr:GetDownloadUrlForLayer",
      "ecr:InitiateLayerUpload",
      "ecr:ListImages",
      "ecr:ListTagsForResource",
      "ecr:PutImage",
      "ecr:PutImageScanningConfiguration",
      "ecr:PutImageTagMutability",
      "ecr:TagResource",
      "ecr:UntagResource",
      "ecr:UploadLayerPart",
    ]
    resources = [local.ecr_repository_arn]

    condition {
      test     = "StringEquals"
      variable = "aws:RequestedRegion"
      values   = [var.aws_region]
    }
  }

  statement {
    sid    = "ManageNamedECSResources"
    effect = "Allow"
    actions = [
      "ecs:CreateCluster",
      "ecs:CreateService",
      "ecs:DeleteCluster",
      "ecs:DeleteService",
      "ecs:DescribeClusters",
      "ecs:DescribeServices",
      "ecs:DescribeTasks",
      "ecs:ListServiceDeployments",
      "ecs:ListTagsForResource",
      "ecs:ListTasks",
      "ecs:StopTask",
      "ecs:TagResource",
      "ecs:UntagResource",
      "ecs:UpdateService",
    ]
    resources = [
      local.ecs_cluster_arn,
      local.ecs_service_arn,
      local.ecs_task_arn,
      local.ecs_task_def_arn,
    ]

    condition {
      test     = "StringEquals"
      variable = "aws:RequestedRegion"
      values   = [var.aws_region]
    }
  }

  statement {
    sid    = "DeregisterTaskDefinition"
    effect = "Allow"
    actions = [
      "ecs:DeregisterTaskDefinition",
    ]
    resources = ["*"]

    condition {
      test     = "StringEquals"
      variable = "aws:RequestedRegion"
      values   = [var.aws_region]
    }
  }

  statement {
    sid    = "RegisterTaggedTaskDefinition"
    effect = "Allow"
    actions = [
      "ecs:RegisterTaskDefinition",
    ]
    resources = ["*"]

    condition {
      test     = "StringEquals"
      variable = "aws:RequestedRegion"
      values   = [var.aws_region]
    }

    condition {
      test     = "StringEquals"
      variable = "aws:RequestTag/Project"
      values   = [var.project_tag]
    }
  }

  statement {
    sid    = "ReadECSAccountMetadata"
    effect = "Allow"
    actions = [
      "ecs:DescribeTaskDefinition",
      "ecs:ListClusters",
      "ecs:ListServices",
      "ecs:ListTaskDefinitions",
    ]
    resources = ["*"]

    condition {
      test     = "StringEquals"
      variable = "aws:RequestedRegion"
      values   = [var.aws_region]
    }
  }

  statement {
    sid    = "CreateTaggedELBv2Resources"
    effect = "Allow"
    actions = [
      "elasticloadbalancing:CreateLoadBalancer",
      "elasticloadbalancing:CreateTargetGroup",
    ]
    resources = ["*"]

    condition {
      test     = "StringEquals"
      variable = "aws:RequestedRegion"
      values   = [var.aws_region]
    }

    condition {
      test     = "StringEquals"
      variable = "aws:RequestTag/Project"
      values   = [var.project_tag]
    }
  }

  statement {
    sid    = "ManageNamedELBv2Resources"
    effect = "Allow"
    actions = [
      "elasticloadbalancing:AddTags",
      "elasticloadbalancing:CreateListener",
      "elasticloadbalancing:DeleteListener",
      "elasticloadbalancing:DeleteLoadBalancer",
      "elasticloadbalancing:DeleteTargetGroup",
      "elasticloadbalancing:ModifyLoadBalancerAttributes",
      "elasticloadbalancing:ModifyTargetGroup",
      "elasticloadbalancing:ModifyTargetGroupAttributes",
      "elasticloadbalancing:RemoveTags",
    ]
    resources = [
      local.load_balancer_arn,
      local.target_group_arn,
      local.listener_arn,
    ]

    condition {
      test     = "StringEquals"
      variable = "aws:RequestedRegion"
      values   = [var.aws_region]
    }
  }

  statement {
    sid    = "DescribeRegionalELBv2Resources"
    effect = "Allow"
    actions = [
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
    ]
    resources = ["*"]

    condition {
      test     = "StringEquals"
      variable = "aws:RequestedRegion"
      values   = [var.aws_region]
    }
  }

  statement {
    sid    = "UseTaggedVpcForNetworkCreation"
    effect = "Allow"
    actions = [
      "ec2:CreateNatGateway",
      "ec2:CreateRouteTable",
      "ec2:CreateSecurityGroup",
      "ec2:CreateSubnet",
    ]
    resources = [local.vpc_arn]

    condition {
      test     = "StringEquals"
      variable = "aws:RequestedRegion"
      values   = [var.aws_region]
    }

    condition {
      test     = "StringEquals"
      variable = "aws:ResourceTag/Project"
      values   = [var.project_tag]
    }
  }

  statement {
    sid     = "UseTaggedNatGatewayDependencies"
    effect  = "Allow"
    actions = ["ec2:CreateNatGateway"]
    resources = [
      local.elastic_ip_arn,
      local.subnet_arn,
    ]

    condition {
      test     = "StringEquals"
      variable = "aws:RequestedRegion"
      values   = [var.aws_region]
    }

    condition {
      test     = "StringEquals"
      variable = "aws:ResourceTag/Project"
      values   = [var.project_tag]
    }
  }

  statement {
    sid    = "CreateTaggedNetworkResources"
    effect = "Allow"
    actions = [
      "ec2:AllocateAddress",
      "ec2:CreateInternetGateway",
      "ec2:CreateNatGateway",
      "ec2:CreateRouteTable",
      "ec2:CreateSecurityGroup",
      "ec2:CreateSubnet",
      "ec2:CreateTags",
      "ec2:CreateVpc",
    ]
    resources = [
      local.elastic_ip_arn,
      local.internet_gateway_arn,
      local.nat_gateway_arn,
      local.route_table_arn,
      local.security_group_arn,
      local.subnet_arn,
      local.vpc_arn,
    ]

    condition {
      test     = "StringEquals"
      variable = "aws:RequestedRegion"
      values   = [var.aws_region]
    }

    condition {
      test     = "StringEquals"
      variable = "aws:RequestTag/Project"
      values   = [var.project_tag]
    }
  }

  statement {
    sid     = "TagNewSecurityGroupRules"
    effect  = "Allow"
    actions = ["ec2:CreateTags"]
    resources = [
      local.security_group_rule_arn,
    ]

    condition {
      test     = "StringEquals"
      variable = "aws:RequestedRegion"
      values   = [var.aws_region]
    }

    condition {
      test     = "StringEquals"
      variable = "aws:RequestTag/Project"
      values   = [var.project_tag]
    }

    condition {
      test     = "StringEquals"
      variable = "ec2:CreateAction"
      values = [
        "AuthorizeSecurityGroupEgress",
        "AuthorizeSecurityGroupIngress",
      ]
    }
  }

  statement {
    sid    = "ManageTaggedNetworkResources"
    effect = "Allow"
    actions = [
      "ec2:DeleteInternetGateway",
      "ec2:DeleteNatGateway",
      "ec2:DeleteRouteTable",
      "ec2:DeleteSecurityGroup",
      "ec2:DeleteSubnet",
      "ec2:DeleteTags",
      "ec2:DeleteVpc",
      "ec2:ModifySubnetAttribute",
      "ec2:ModifyVpcAttribute",
      "ec2:ReleaseAddress",
    ]
    resources = ["*"]

    condition {
      test     = "StringEquals"
      variable = "aws:RequestedRegion"
      values   = [var.aws_region]
    }

    condition {
      test     = "StringEquals"
      variable = "aws:ResourceTag/Project"
      values   = [var.project_tag]
    }
  }

  statement {
    sid    = "ManageRegionalNetworkRelationships"
    effect = "Allow"
    actions = [
      "ec2:AssociateRouteTable",
      "ec2:AttachInternetGateway",
      "ec2:AuthorizeSecurityGroupEgress",
      "ec2:AuthorizeSecurityGroupIngress",
      "ec2:CreateRoute",
      "ec2:DeleteRoute",
      "ec2:DisassociateRouteTable",
      "ec2:DetachInternetGateway",
      "ec2:RevokeSecurityGroupEgress",
      "ec2:RevokeSecurityGroupIngress",
    ]
    resources = ["*"]

    condition {
      test     = "StringEquals"
      variable = "aws:RequestedRegion"
      values   = [var.aws_region]
    }
  }

  statement {
    sid    = "DescribeRegionalNetworkResources"
    effect = "Allow"
    actions = [
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
    ]
    resources = ["*"]

    condition {
      test     = "StringEquals"
      variable = "aws:RequestedRegion"
      values   = [var.aws_region]
    }
  }

  statement {
    sid    = "ManageExactECSExecutionRole"
    effect = "Allow"
    actions = [
      "iam:CreateRole",
      "iam:DeleteRole",
      "iam:DeleteRolePolicy",
      "iam:GetRole",
      "iam:GetRolePolicy",
      "iam:ListAttachedRolePolicies",
      "iam:ListInstanceProfilesForRole",
      "iam:ListRolePolicies",
      "iam:ListRoleTags",
      "iam:PutRolePolicy",
      "iam:TagRole",
      "iam:UntagRole",
      "iam:UpdateAssumeRolePolicy",
    ]
    resources = [local.ecs_execution_role_arn]
  }

  statement {
    sid       = "PassExactECSExecutionRole"
    effect    = "Allow"
    actions   = ["iam:PassRole"]
    resources = [local.ecs_execution_role_arn]

    condition {
      test     = "StringEquals"
      variable = "iam:PassedToService"
      values   = ["ecs-tasks.amazonaws.com"]
    }
  }

  statement {
    sid    = "CreateRequiredServiceLinkedRoles"
    effect = "Allow"
    actions = [
      "iam:CreateServiceLinkedRole",
    ]
    resources = ["*"]

    condition {
      test     = "StringEquals"
      variable = "iam:AWSServiceName"
      values = [
        "ecs.amazonaws.com",
        "elasticloadbalancing.amazonaws.com",
      ]
    }
  }

  statement {
    sid    = "ManageExactApplicationLogGroup"
    effect = "Allow"
    actions = [
      "logs:CreateLogGroup",
      "logs:DeleteLogGroup",
      "logs:DescribeLogStreams",
      "logs:FilterLogEvents",
      "logs:GetLogEvents",
      "logs:ListTagsForResource",
      "logs:PutRetentionPolicy",
      "logs:TagResource",
      "logs:UntagResource",
    ]
    resources = [
      local.log_group_arn,
      "${local.log_group_arn}:*",
    ]

    condition {
      test     = "StringEquals"
      variable = "aws:RequestedRegion"
      values   = [var.aws_region]
    }
  }

  statement {
    sid       = "DescribeRegionalLogGroups"
    effect    = "Allow"
    actions   = ["logs:DescribeLogGroups"]
    resources = ["*"]

    condition {
      test     = "StringEquals"
      variable = "aws:RequestedRegion"
      values   = [var.aws_region]
    }
  }
}

resource "aws_iam_role" "cd_lifecycle" {
  name                 = var.cd_role_name
  assume_role_policy   = data.aws_iam_policy_document.cd_assume_role.json
  max_session_duration = 3600

  tags = {
    Name = var.cd_role_name
  }
}

resource "aws_iam_role_policy" "cd_lifecycle" {
  name   = "${var.cd_role_name}-application-lifecycle"
  role   = aws_iam_role.cd_lifecycle.id
  policy = data.aws_iam_policy_document.cd_lifecycle.json
}
