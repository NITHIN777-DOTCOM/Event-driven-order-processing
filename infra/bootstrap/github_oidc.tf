# =============================================================================
# GitHub Actions -> AWS with OIDC: short-lived credentials, NO stored access keys.
#
# GitHub signs a JWT for each workflow run; AWS STS trusts it via this OIDC provider and lets the
# run assume a role ONLY if the token's claims match the trust policy below:
#   deploy role: this repository, branch main only        (sub = <prefix>:ref:refs/heads/main)
#   plan role:   pull requests in this repository only    (sub = <prefix>:pull_request)
# Forks can't assume either role (their sub names a different repo).
#
# This repo uses GitHub's "immutable subject" format, which embeds the numeric owner and repo IDs:
#   repo:NITHIN777-DOTCOM@180836916/Event-driven-order-processing@1429553651
# (check with: gh api repos/<owner>/<repo>/actions/oidc/customization/sub). That's stronger than the
# name-only form: a deleted-and-recreated repo with the same name gets a different ID and can't assume the roles.
# =============================================================================

locals {
  github_sub_prefix = var.github_oidc_subject_prefix
  # Every resource infra/main manages is named order-saga-*; the deploy role is scoped to that prefix.
  p = var.project_prefix
  # Must match the Project tag in the provider default_tags (versions.tf): Cognito access is gated on it.
  project_tag = "aws-order-saga"
}

resource "aws_iam_openid_connect_provider" "github" {
  url            = "https://token.actions.githubusercontent.com"
  client_id_list = ["sts.amazonaws.com"]
  # AWS validates GitHub's certificate chain itself now; these are GitHub's published thumbprints.
  thumbprint_list = ["6938fd4d98bab03faadb97b34396831e3780aea1", "1c58a3a8518e8759bf075b76b750d4f2df264fcd"]

  tags = {
    Name        = "github-actions-oidc"
    Description = module.tags.description["github_oidc"]
  }
}

data "aws_iam_policy_document" "github_trust" {
  for_each = {
    deploy = "${local.github_sub_prefix}:ref:refs/heads/main"
    plan   = "${local.github_sub_prefix}:pull_request"
  }

  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]
    principals {
      type        = "Federated"
      identifiers = [aws_iam_openid_connect_provider.github.arn]
    }
    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }
    # StringEquals (not StringLike): exactly this repo and this trigger, nothing else.
    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:sub"
      values   = [each.value]
    }
  }
}

# -----------------------------------------------------------------------------
# Plan role (pull requests): read-only + the Terraform state lock file.
# -----------------------------------------------------------------------------
resource "aws_iam_role" "github_plan" {
  name                 = "${local.p}-github-plan-role"
  description          = "GitHub Actions on pull requests of ${var.github_repository}: read-only, for terraform plan"
  assume_role_policy   = data.aws_iam_policy_document.github_trust["plan"].json
  max_session_duration = 3600
}

resource "aws_iam_role_policy_attachment" "github_plan_readonly" {
  role       = aws_iam_role.github_plan.name
  policy_arn = "arn:aws:iam::aws:policy/ReadOnlyAccess"
}

# terraform plan takes the S3-native state lock (main/terraform.tfstate.tflock): allow writing ONLY that key.
data "aws_iam_policy_document" "github_plan_lock" {
  statement {
    sid       = "StateLockFileOnly"
    actions   = ["s3:PutObject", "s3:DeleteObject"]
    resources = ["${aws_s3_bucket.tfstate.arn}/main/terraform.tfstate.tflock"]
  }
}

resource "aws_iam_role_policy" "github_plan_lock" {
  name   = "${local.p}-github-plan-state-lock"
  role   = aws_iam_role.github_plan.id
  policy = data.aws_iam_policy_document.github_plan_lock.json
}

# -----------------------------------------------------------------------------
# Deploy role (main only): manage exactly the services infra/main uses, scoped to order-saga-* names
# wherever the service supports resource-level permissions. No AdministratorAccess.
# -----------------------------------------------------------------------------
data "aws_iam_policy_document" "github_deploy" {
  statement {
    sid     = "TerraformState"
    actions = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject", "s3:ListBucket", "s3:GetBucketVersioning"]
    resources = [
      aws_s3_bucket.tfstate.arn,
      "${aws_s3_bucket.tfstate.arn}/main/*",
    ]
  }
  statement {
    sid       = "ProtectStateBucket"
    effect    = "Deny"
    actions   = ["s3:DeleteBucket", "s3:PutBucketPolicy", "s3:DeleteBucketPolicy", "s3:PutLifecycleConfiguration"]
    resources = [aws_s3_bucket.tfstate.arn]
  }
  statement {
    sid       = "FrontendBucket"
    actions   = ["s3:*"]
    resources = ["arn:aws:s3:::${local.p}-frontend-*", "arn:aws:s3:::${local.p}-frontend-*/*"]
  }
  statement {
    sid       = "Lambda"
    actions   = ["lambda:*"]
    resources = ["arn:aws:lambda:${var.region}:${local.account_id}:function:${local.p}-*"]
  }
  statement {
    sid = "LambdaEventSourceMappingsAndLayer"
    actions = [
      "lambda:CreateEventSourceMapping", "lambda:GetEventSourceMapping", "lambda:UpdateEventSourceMapping",
      "lambda:DeleteEventSourceMapping", "lambda:ListEventSourceMappings", "lambda:ListTags", "lambda:TagResource",
    ]
    resources = ["*"] # event source mappings are identified by a random UUID
  }
  statement {
    sid       = "PowertoolsLayer"
    actions   = ["lambda:GetLayerVersion"]
    resources = ["arn:aws:lambda:${var.region}:017000801446:layer:AWSLambdaPowertoolsPythonV3-*"]
  }
  statement {
    sid     = "StepFunctions"
    actions = ["states:*"]
    resources = [
      "arn:aws:states:${var.region}:${local.account_id}:stateMachine:${local.p}-*",
      "arn:aws:states:${var.region}:${local.account_id}:execution:${local.p}-*",
    ]
  }
  statement {
    sid       = "StepFunctionsValidate"
    actions   = ["states:ValidateStateMachineDefinition", "states:ListStateMachines"]
    resources = ["*"]
  }
  statement {
    sid     = "DynamoDB"
    actions = ["dynamodb:*"]
    resources = [
      "arn:aws:dynamodb:${var.region}:${local.account_id}:table/${local.p}-*",
      "arn:aws:dynamodb:${var.region}:${local.account_id}:table/${local.p}-*/index/*",
    ]
  }
  statement {
    sid       = "SQS"
    actions   = ["sqs:*"]
    resources = ["arn:aws:sqs:${var.region}:${local.account_id}:${local.p}-*"]
  }
  statement {
    sid       = "SNS"
    actions   = ["sns:*"]
    resources = ["arn:aws:sns:${var.region}:${local.account_id}:${local.p}-*"]
  }
  statement {
    sid       = "APIGateway"
    actions   = ["apigateway:*"]
    resources = ["arn:aws:apigateway:${var.region}::/apis", "arn:aws:apigateway:${var.region}::/apis/*", "arn:aws:apigateway:${var.region}::/tags/*"]
  }
  statement {
    sid     = "LogGroups"
    actions = ["logs:*"]
    resources = [
      "arn:aws:logs:${var.region}:${local.account_id}:log-group:/aws/lambda/${local.p}-*",
      "arn:aws:logs:${var.region}:${local.account_id}:log-group:/aws/vendedlogs/states/${local.p}-*",
      "arn:aws:logs:${var.region}:${local.account_id}:log-group:/aws/apigateway/${local.p}-*",
    ]
  }
  # Log delivery set-up (Step Functions / API access logs), saved queries and describe calls have no
  # resource-level permissions, so they need "*".
  statement {
    sid = "LogsAccountLevel"
    actions = [
      "logs:DescribeLogGroups", "logs:CreateLogDelivery", "logs:GetLogDelivery", "logs:UpdateLogDelivery",
      "logs:DeleteLogDelivery", "logs:ListLogDeliveries", "logs:PutResourcePolicy", "logs:DescribeResourcePolicies",
      "logs:PutQueryDefinition", "logs:DescribeQueryDefinitions", "logs:DeleteQueryDefinition", "logs:ListTagsForResource",
    ]
    resources = ["*"]
  }
  statement {
    sid     = "CloudWatchAlarmsAndDashboard"
    actions = ["cloudwatch:*"]
    resources = [
      "arn:aws:cloudwatch:${var.region}:${local.account_id}:alarm:${local.p}-*",
      "arn:aws:cloudwatch::${local.account_id}:dashboard/${local.p}-*",
    ]
  }
  statement {
    sid       = "CloudWatchDescribe"
    actions   = ["cloudwatch:DescribeAlarms", "cloudwatch:ListTagsForResource"]
    resources = ["*"]
  }
  statement {
    sid = "CloudFront"
    actions = [
      "cloudfront:CreateDistribution", "cloudfront:UpdateDistribution", "cloudfront:GetDistribution",
      "cloudfront:GetDistributionConfig", "cloudfront:DeleteDistribution", "cloudfront:TagResource",
      "cloudfront:ListTagsForResource", "cloudfront:CreateInvalidation", "cloudfront:GetInvalidation",
      "cloudfront:CreateOriginAccessControl", "cloudfront:GetOriginAccessControl", "cloudfront:UpdateOriginAccessControl",
      "cloudfront:DeleteOriginAccessControl", "cloudfront:ListOriginAccessControls",
      "cloudfront:ListCachePolicies", "cloudfront:GetCachePolicy",
      "cloudfront:ListResponseHeadersPolicies", "cloudfront:GetResponseHeadersPolicy",
    ]
    resources = ["*"] # distribution IDs are random; CloudFront is global
  }
  statement {
    sid = "IAMProjectRolesOnly"
    actions = [
      "iam:CreateRole", "iam:DeleteRole", "iam:GetRole", "iam:UpdateRole", "iam:UpdateAssumeRolePolicy",
      "iam:TagRole", "iam:UntagRole", "iam:ListRoleTags", "iam:PutRolePolicy", "iam:GetRolePolicy",
      "iam:DeleteRolePolicy", "iam:ListRolePolicies", "iam:ListAttachedRolePolicies",
      "iam:ListInstanceProfilesForRole",
    ]
    resources = ["arn:aws:iam::${local.account_id}:role/${local.p}-*"]
  }
  # PassRole only to the services that actually run with a project role: Lambda functions, the Step
  # Functions state machine and (step 1.1) the EventBridge pipe. Nothing else can be handed a role.
  statement {
    sid       = "PassProjectRolesToProjectServices"
    actions   = ["iam:PassRole"]
    resources = ["arn:aws:iam::${local.account_id}:role/${local.p}-*"]
    condition {
      test     = "StringEquals"
      variable = "iam:PassedToService"
      values   = ["lambda.amazonaws.com", "states.amazonaws.com", "pipes.amazonaws.com"]
    }
  }

  # EventBridge Pipes (transactional outbox: orders stream -> pipe -> SQS). Pipe names are chosen by
  # us, so every action is scoped by ARN to order-saga-* pipes.
  statement {
    sid = "EventBridgePipes"
    actions = [
      "pipes:CreatePipe", "pipes:UpdatePipe", "pipes:DeletePipe", "pipes:DescribePipe",
      "pipes:StartPipe", "pipes:StopPipe",
      "pipes:TagResource", "pipes:UntagResource", "pipes:ListTagsForResource",
    ]
    resources = ["arn:aws:pipes:${var.region}:${local.account_id}:pipe/${local.p}-*"]
  }
  # DynamoDB Streams need nothing extra: the "DynamoDB" statement above already grants dynamodb:* on
  # table/order-saga-*, and stream ARNs live under it (table/<name>/stream/<label>).

  # Cognito user pools get a random ID (ap-south-1_AbC123), so they can't be scoped by name. Instead:
  #   create:     only if the request tags the pool Project=aws-order-saga (provider default_tags do)
  #   everything: only on pools that already carry that tag (so foreign pools are untouchable)
  statement {
    sid       = "CognitoCreateTaggedUserPool"
    actions   = ["cognito-idp:CreateUserPool"]
    resources = ["*"] # the pool doesn't exist yet, so there is no ARN to scope to
    condition {
      test     = "StringEquals"
      variable = "aws:RequestTag/Project"
      values   = [local.project_tag]
    }
  }
  statement {
    sid = "CognitoManageProjectUserPools"
    actions = [
      # pool
      "cognito-idp:DescribeUserPool", "cognito-idp:UpdateUserPool", "cognito-idp:DeleteUserPool",
      "cognito-idp:GetUserPoolMfaConfig", "cognito-idp:SetUserPoolMfaConfig", "cognito-idp:AddCustomAttributes",
      "cognito-idp:TagResource", "cognito-idp:UntagResource", "cognito-idp:ListTagsForResource",
      # app clients (the AWS provider lists a pool's clients before updating one)
      "cognito-idp:ListUserPoolClients",
      "cognito-idp:CreateUserPoolClient", "cognito-idp:DescribeUserPoolClient",
      "cognito-idp:UpdateUserPoolClient", "cognito-idp:DeleteUserPoolClient",
      # hosted domain + managed login
      "cognito-idp:CreateUserPoolDomain", "cognito-idp:UpdateUserPoolDomain", "cognito-idp:DeleteUserPoolDomain",
      "cognito-idp:CreateManagedLoginBranding", "cognito-idp:DescribeManagedLoginBranding",
      "cognito-idp:DescribeManagedLoginBrandingByClient", "cognito-idp:UpdateManagedLoginBranding",
      "cognito-idp:DeleteManagedLoginBranding",
      # the demo/CI test users (step 1.2)
      "cognito-idp:AdminCreateUser", "cognito-idp:AdminGetUser", "cognito-idp:AdminDeleteUser",
      "cognito-idp:AdminSetUserPassword", "cognito-idp:AdminUpdateUserAttributes",
      # the CI smoke test signs in as a test user through the "automation" app client (ADMIN_USER_PASSWORD_AUTH)
      "cognito-idp:AdminInitiateAuth",
    ]
    resources = ["arn:aws:cognito-idp:${var.region}:${local.account_id}:userpool/*"]
    condition {
      test     = "StringEquals"
      variable = "aws:ResourceTag/Project"
      values   = [local.project_tag]
    }
  }
  statement {
    sid = "CognitoReadOnlyUnscoped"
    # DescribeUserPoolDomain is looked up by domain prefix, not pool ARN; ListUserPools is account-wide.
    # Both are read-only and have no resource type, so they need "*".
    actions   = ["cognito-idp:DescribeUserPoolDomain", "cognito-idp:ListUserPools"]
    resources = ["*"]
  }

  # EventBridge Scheduler (step 2.2, checkout holds): Terraform only manages the schedule GROUP. The one-time
  # schedules inside it are created and deleted at run time by the holds Lambda (with its own role), never by CI.
  statement {
    sid = "SchedulerProjectGroups"
    actions = [
      "scheduler:CreateScheduleGroup", "scheduler:GetScheduleGroup", "scheduler:DeleteScheduleGroup",
      "scheduler:TagResource", "scheduler:UntagResource", "scheduler:ListTagsForResource",
    ]
    resources = ["arn:aws:scheduler:${var.region}:${local.account_id}:schedule-group/${local.p}-*"]
  }

  # SSM Parameter Store under /order-saga/* (e.g. the test-user password as a SecureString). It uses the
  # AWS-managed key aws/ssm, whose key policy already lets SSM use it for this account: no kms:* grant.
  statement {
    sid = "SsmProjectParameters"
    actions = [
      "ssm:PutParameter", "ssm:GetParameter", "ssm:GetParameters", "ssm:DeleteParameter",
      "ssm:AddTagsToResource", "ssm:RemoveTagsFromResource", "ssm:ListTagsForResource",
    ]
    resources = ["arn:aws:ssm:${var.region}:${local.account_id}:parameter/${local.p}/*"]
  }
  statement {
    sid       = "SsmDescribeParameters"
    actions   = ["ssm:DescribeParameters"] # read-only, metadata only; the API has no resource type
    resources = ["*"]
  }
  # Never let the pipeline edit its own trust or permissions (no privilege escalation).
  statement {
    sid       = "NoSelfEscalation"
    effect    = "Deny"
    actions   = ["iam:*"]
    resources = [aws_iam_role.github_plan.arn, "arn:aws:iam::${local.account_id}:role/${local.p}-github-deploy-role"]
  }
  statement {
    sid       = "ReadOnlyHelpers"
    actions   = ["budgets:ViewBudget", "ssm:GetParameter", "sts:GetCallerIdentity", "xray:GetSamplingRules"]
    resources = ["*"]
  }
}

resource "aws_iam_role" "github_deploy" {
  name                 = "${local.p}-github-deploy-role"
  description          = "GitHub Actions on main of ${var.github_repository}: terraform apply + frontend deploy for order-saga"
  assume_role_policy   = data.aws_iam_policy_document.github_trust["deploy"].json
  max_session_duration = 3600
}

resource "aws_iam_role_policy" "github_deploy" {
  name   = "${local.p}-github-deploy-policy"
  role   = aws_iam_role.github_deploy.id
  policy = data.aws_iam_policy_document.github_deploy.json
}
