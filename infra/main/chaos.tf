# =============================================================================
# Chaos experiments (step 3.2): the fault-injection configuration bucket.
#
# Planned with AWS FIS; FIS is not available on this account's AWS Free plan (every call answers
# SubscriptionRequiredException), so the faults are injected by our own code with the same contract
# (src/common/chaos.py):
#   scripts/chaos_run.py writes ONE object, faults/active.json: which functions, error or delay, what percentage,
#   and an expiry of at most 15 minutes. The 9 saga Lambdas read it (cached 30 s) while CHAOS_ENABLED is true and
#   inject the fault only into orders of that chaos run (order field chaosRun), never into storefront orders.
#   Stop condition: the harness deletes the object when the order-saga-invariant-violation alarm fires.
#
# The bucket keeps its first name (order-saga-fis-config-<account>): renaming an S3 bucket means replacing it.
# Never run an experiment during a demo.
# =============================================================================

locals {
  chaos_fault_prefix = "faults"
  chaos_fault_key    = "${local.chaos_fault_prefix}/active.json"
}

# ---------------------------------------------------------------------------
# Config bucket: private, SSE-S3 (AWS-managed), TLS only, and old configs cleaned up by a lifecycle rule.
# ---------------------------------------------------------------------------
resource "aws_s3_bucket" "fis_config" {
  bucket        = "${var.project_prefix}-fis-config-${local.account_id}"
  force_destroy = false

  tags = {
    Name        = "${var.project_prefix}-fis-config-${local.account_id}"
    Description = module.tags.description["fis_config_bucket"]
  }
}

resource "aws_s3_bucket_public_access_block" "fis_config" {
  bucket                  = aws_s3_bucket.fis_config.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_ownership_controls" "fis_config" {
  bucket = aws_s3_bucket.fis_config.id
  rule {
    object_ownership = "BucketOwnerEnforced" # ACLs off
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "fis_config" {
  bucket = aws_s3_bucket.fis_config.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256" # SSE-S3, no customer-managed key
    }
  }
}

# The harness deletes the configuration when a run ends (and it has expired by then anyway); this catches anything
# left behind by an interrupted run.
resource "aws_s3_bucket_lifecycle_configuration" "fis_config" {
  bucket = aws_s3_bucket.fis_config.id
  rule {
    id     = "expire-old-fault-configs"
    status = "Enabled"
    filter {
      prefix = "${local.chaos_fault_prefix}/"
    }
    expiration {
      days = 1
    }
    noncurrent_version_expiration {
      noncurrent_days = 1
    }
    abort_incomplete_multipart_upload {
      days_after_initiation = 1
    }
  }
}

data "aws_iam_policy_document" "fis_config_bucket" {
  statement {
    sid       = "DenyInsecureTransport"
    effect    = "Deny"
    actions   = ["s3:*"]
    resources = [aws_s3_bucket.fis_config.arn, "${aws_s3_bucket.fis_config.arn}/*"]
    principals {
      type        = "*"
      identifiers = ["*"]
    }
    condition {
      test     = "Bool"
      variable = "aws:SecureTransport"
      values   = ["false"]
    }
  }
}

resource "aws_s3_bucket_policy" "fis_config" {
  bucket     = aws_s3_bucket.fis_config.id
  policy     = data.aws_iam_policy_document.fis_config_bucket.json
  depends_on = [aws_s3_bucket_public_access_block.fis_config]
}
