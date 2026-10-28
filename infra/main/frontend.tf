# =============================================================================
# Storefront hosting: a PRIVATE S3 bucket behind CloudFront, using Origin Access Control (OAC).
# Only this distribution can read the bucket. The built React app is uploaded by
# scripts/deploy_frontend.py; Terraform owns config.json (API URL) so it always matches the backend.
# =============================================================================

resource "aws_s3_bucket" "frontend" {
  bucket = "${var.project_prefix}-frontend-${local.account_id}"

  tags = {
    Name        = "${var.project_prefix}-frontend-${local.account_id}"
    Description = "Storefront static files - React build - served only through CloudFront"
  }
}

resource "aws_s3_bucket_public_access_block" "frontend" {
  bucket = aws_s3_bucket.frontend.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "frontend" {
  bucket = aws_s3_bucket.frontend.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_cloudfront_origin_access_control" "frontend" {
  name                              = "${var.project_prefix}-frontend-oac"
  description                       = "Lets the order-saga storefront distribution read the private S3 bucket"
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

# AWS-managed policies: cache by Cache-Control headers (gzip/brotli aware), and standard security headers.
data "aws_cloudfront_cache_policy" "optimized" {
  name = "Managed-CachingOptimized"
}

data "aws_cloudfront_response_headers_policy" "security" {
  name = "Managed-SecurityHeadersPolicy"
}

resource "aws_cloudfront_distribution" "frontend" {
  enabled             = true
  comment             = "order-saga storefront"
  default_root_object = "index.html"
  price_class         = "PriceClass_200" # includes India edge locations, excludes the priciest regions
  is_ipv6_enabled     = true
  http_version        = "http2and3"

  origin {
    origin_id                = "s3-storefront"
    domain_name              = aws_s3_bucket.frontend.bucket_regional_domain_name
    origin_access_control_id = aws_cloudfront_origin_access_control.frontend.id
  }

  default_cache_behavior {
    target_origin_id           = "s3-storefront"
    viewer_protocol_policy     = "redirect-to-https"
    allowed_methods            = ["GET", "HEAD", "OPTIONS"]
    cached_methods             = ["GET", "HEAD"]
    cache_policy_id            = data.aws_cloudfront_cache_policy.optimized.id
    response_headers_policy_id = data.aws_cloudfront_response_headers_policy.security.id
    compress                   = true
  }

  # SPA fallback: deep links such as /orders/ORD-... aren't files in S3. A private bucket answers
  # 403 for a missing key (404 if ListBucket were allowed), so both are served index.html and React
  # Router takes over.
  custom_error_response {
    error_code            = 403
    response_code         = 200
    response_page_path    = "/index.html"
    error_caching_min_ttl = 0
  }

  custom_error_response {
    error_code            = 404
    response_code         = 200
    response_page_path    = "/index.html"
    error_caching_min_ttl = 0
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  viewer_certificate {
    cloudfront_default_certificate = true
  }

  tags = {
    Name        = "${var.project_prefix}-storefront"
    Description = "CDN for the order-saga storefront - HTTPS only - OAC to a private S3 bucket"
  }
}

# Bucket policy: only THIS distribution (checked via AWS:SourceArn) may read objects.
data "aws_iam_policy_document" "frontend_bucket" {
  statement {
    sid       = "AllowCloudFrontOACRead"
    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.frontend.arn}/*"]

    principals {
      type        = "Service"
      identifiers = ["cloudfront.amazonaws.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "AWS:SourceArn"
      values   = [aws_cloudfront_distribution.frontend.arn]
    }
  }

  statement {
    sid     = "DenyInsecureTransport"
    effect  = "Deny"
    actions = ["s3:*"]
    principals {
      type        = "*"
      identifiers = ["*"]
    }
    resources = [aws_s3_bucket.frontend.arn, "${aws_s3_bucket.frontend.arn}/*"]
    condition {
      test     = "Bool"
      variable = "aws:SecureTransport"
      values   = ["false"]
    }
  }
}

resource "aws_s3_bucket_policy" "frontend" {
  bucket     = aws_s3_bucket.frontend.id
  policy     = data.aws_iam_policy_document.frontend_bucket.json
  depends_on = [aws_s3_bucket_public_access_block.frontend]
}

# Runtime config read by the app at startup (GET /config.json). no-cache, so a backend change shows up at once.
# Written here (not by deploy_frontend.py) so it changes in the same apply as the API and the Cognito clients.
# Nothing in it is secret: the pool and SPA client IDs are public by design (a PKCE client has no secret).
resource "aws_s3_object" "frontend_config" {
  bucket        = aws_s3_bucket.frontend.id
  key           = "config.json"
  content_type  = "application/json"
  cache_control = "no-cache"
  content = jsonencode({
    apiUrl = trimsuffix(aws_apigatewayv2_stage.default.invoke_url, "/")
    region = var.region
    auth = {
      authority  = "https://cognito-idp.${var.region}.amazonaws.com/${aws_cognito_user_pool.users.id}"
      userPoolId = aws_cognito_user_pool.users.id
      clientId   = aws_cognito_user_pool_client.spa.id
      domain     = "https://${aws_cognito_user_pool_domain.users.domain}.auth.${var.region}.amazoncognito.com"
    }
  })
}
