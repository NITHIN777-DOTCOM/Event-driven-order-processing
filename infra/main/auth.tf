# Authentication: Amazon Cognito user pool + managed login (step 1.2).
#
#   Browser (SPA)  --authorization code + PKCE-->  managed login (order-saga-<account>.auth...)  -> ID/access tokens
#   Scripts / CI   --AdminInitiateAuth (IAM-signed)-->  "automation" client                       -> ID/access tokens
#   Cognito        --pre-token-generation trigger (order-saga-pre-token)-->  adds email + email_verified to ACCESS tokens
#   API Gateway    --JWT authorizer-->  checks issuer + audience (both clients) before any Lambda runs; the API
#                                       is called with the ACCESS token (step 2.0)
#
# Cost: ESSENTIALS is the cheapest feature plan with managed login. 10,000 monthly active users are free
# (indefinitely, not a 12-month trial); this demo has a handful. No paid add-ons: no threat protection
# (Plus plan), no M2M client-credentials tokens (scripts sign in as real test users instead), no SMS.

locals {
  # Where the managed login page may send users back to: the storefront and the local Vite dev server.
  auth_origins = ["https://${aws_cloudfront_distribution.frontend.domain_name}", "http://localhost:5173"]
}

resource "aws_cognito_user_pool" "users" {
  name           = "${var.project_prefix}-users"
  user_pool_tier = "ESSENTIALS"

  # Email is the username; users sign themselves up and prove they own the address with a code.
  username_attributes      = ["email"]
  auto_verified_attributes = ["email"]
  username_configuration {
    case_sensitive = false # Alice@x.com and alice@x.com are the same user
  }
  admin_create_user_config {
    allow_admin_create_user_only = false # self-sign-up on
  }
  verification_message_template {
    default_email_option = "CONFIRM_WITH_CODE"
    email_subject        = "Your Order Saga verification code"
    email_message        = "Your Order Saga verification code is {####}"
  }
  # Cognito's built-in sender: free, no SES setup, but limited to a few dozen emails per day per account.
  # Fine for a demo; production would switch to email_sending_account = "DEVELOPER" with SES.
  email_configuration {
    email_sending_account = "COGNITO_DEFAULT"
  }
  # Changing the email requires verifying the new one first; until then the old, verified one stays.
  user_attribute_update_settings {
    attributes_require_verification_before_update = ["email"]
  }
  account_recovery_setting {
    recovery_mechanism {
      name     = "verified_email"
      priority = 1
    }
  }

  password_policy {
    minimum_length                   = 10
    require_lowercase                = true
    require_uppercase                = true
    require_numbers                  = true
    require_symbols                  = false
    temporary_password_validity_days = 3
    password_history_size            = 0
  }
  sign_in_policy {
    allowed_first_auth_factors = ["PASSWORD"]
  }
  mfa_configuration = "OFF" # demo shop; MFA would be the first thing to turn on for real money

  # Step 2.0: copy email + email_verified into ACCESS tokens, so the API can accept access tokens (the token
  # meant for APIs) instead of ID tokens. Event version V2_0 is the one that can customise access tokens; it
  # needs the Essentials or Plus plan (this pool is Essentials). See src/lambdas/pre_token/handler.py.
  lambda_config {
    pre_token_generation_config {
      lambda_arn     = aws_lambda_function.fn["pre_token"].arn
      lambda_version = "V2_0"
    }
  }

  # The pool holds every user account: refuse to delete it, even from Terraform (clear this first, on purpose).
  deletion_protection = "ACTIVE"
}

# Managed login on a free Cognito prefix domain: https://order-saga-<account id>.auth.ap-south-1.amazoncognito.com
resource "aws_cognito_user_pool_domain" "users" {
  domain                = "${var.project_prefix}-${local.account_id}"
  user_pool_id          = aws_cognito_user_pool.users.id
  managed_login_version = 2 # the new "managed login" pages (version 1 is the classic hosted UI)
}

# The storefront. A browser can't keep a secret, so: public client, no secret, authorization code + PKCE only
# (no implicit flow: tokens never travel in a URL fragment), and NO password API flows: users can only sign
# in through the managed login page.
resource "aws_cognito_user_pool_client" "spa" {
  name         = "spa"
  user_pool_id = aws_cognito_user_pool.users.id

  generate_secret                      = false
  allowed_oauth_flows_user_pool_client = true
  allowed_oauth_flows                  = ["code"]
  allowed_oauth_scopes                 = ["openid", "email", "profile"]
  supported_identity_providers         = ["COGNITO"]
  callback_urls                        = [for o in local.auth_origins : "${o}/auth/callback"]
  logout_urls                          = [for o in local.auth_origins : "${o}/"]

  # No usable password API flow: users can only sign in through the managed login page.
  # An EMPTY list doesn't work: Cognito then applies its defaults, and USER_SRP_AUTH (password) answered with a
  # PASSWORD_VERIFIER challenge on this client (found in the step 1.2 checks). Listing only ALLOW_CUSTOM_AUTH
  # replaces the defaults, and custom auth can't complete because the pool has no custom-auth Lambda triggers.
  # REFRESH_TOKEN_AUTH is left out because refresh-token rotation forbids it; the browser refreshes through
  # the OAuth token endpoint instead, which supports rotation.
  explicit_auth_flows = ["ALLOW_CUSTOM_AUTH"]

  access_token_validity  = 60
  id_token_validity      = 60
  refresh_token_validity = 7
  token_validity_units {
    access_token  = "minutes"
    id_token      = "minutes"
    refresh_token = "days"
  }
  # Every refresh returns a NEW refresh token and retires the old one (after a 10 s grace period for retries),
  # so a stolen refresh token stops working as soon as the real user refreshes.
  refresh_token_rotation {
    feature                    = "ENABLED"
    retry_grace_period_seconds = 10
  }
  enable_token_revocation       = true
  prevent_user_existence_errors = "ENABLED" # "wrong email or password", never "no such user"
}

# Scripts and CI only (smoke_test, e2e_test, ...). They sign in as the test users with AdminInitiateAuth, an
# IAM-signed admin API call: only principals allowed cognito-idp:AdminInitiateAuth on this pool can use it,
# so the password flow is not reachable from the internet. No OAuth flows, no secret (IAM is the gate).
resource "aws_cognito_user_pool_client" "automation" {
  name         = "automation"
  user_pool_id = aws_cognito_user_pool.users.id

  generate_secret                      = false
  allowed_oauth_flows_user_pool_client = false
  explicit_auth_flows                  = ["ALLOW_ADMIN_USER_PASSWORD_AUTH", "ALLOW_REFRESH_TOKEN_AUTH"]

  access_token_validity  = 60
  id_token_validity      = 60
  refresh_token_validity = 1
  token_validity_units {
    access_token  = "minutes"
    id_token      = "minutes"
    refresh_token = "days"
  }
  enable_token_revocation       = true
  prevent_user_existence_errors = "ENABLED"
}

# Only this user pool may invoke the trigger (not any Cognito pool in any account).
resource "aws_lambda_permission" "cognito_pre_token" {
  statement_id  = "AllowInvokeFromOrderSagaUserPool"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.fn["pre_token"].function_name
  principal     = "cognito-idp.amazonaws.com"
  source_arn    = aws_cognito_user_pool.users.arn
}

# Managed login v2 needs a style per app client that shows the page; Cognito's default look is enough.
resource "aws_cognito_managed_login_branding" "spa" {
  user_pool_id                = aws_cognito_user_pool.users.id
  client_id                   = aws_cognito_user_pool_client.spa.id
  use_cognito_provided_values = true
}
