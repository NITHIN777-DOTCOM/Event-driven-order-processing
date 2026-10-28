"""Build the storefront and publish it to S3 + CloudFront.

    python scripts/deploy_frontend.py            # build, upload, invalidate
    python scripts/deploy_frontend.py --no-build # upload the existing frontend/dist
    python scripts/deploy_frontend.py --local-config  # only write frontend/public/config.json for `npm run dev`

Caching strategy:
  assets/*        content-hashed file names -> "public, max-age=31536000, immutable"
  index.html      -> "no-cache" (always revalidated, so a new deploy shows up at once)
  other files     (product photos, favicon) -> 1 day
  config.json     is NOT uploaded here: Terraform owns it (API URL + Cognito pool, SPA client and domain),
                  so it changes in the same apply as those resources.
Then it invalidates /index.html and /config.json and prints the URL.
"""

from __future__ import annotations

import argparse
import json
import mimetypes
import shutil
import subprocess
import time
from pathlib import Path

import boto3

from tf_outputs import load_outputs

FRONTEND = Path(__file__).resolve().parents[1] / "frontend"
DIST = FRONTEND / "dist"

IMMUTABLE = "public, max-age=31536000, immutable"
NO_CACHE = "no-cache"
ONE_DAY = "public, max-age=86400"
CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".json": "application/json",
    ".svg": "image/svg+xml",
    ".webp": "image/webp",
    ".woff2": "font/woff2",
    ".woff": "font/woff",
}
SKIP = {"config.json", "config.example.json"}  # config.json is written by Terraform (infra/main/frontend.tf)


def build() -> None:
    npm = shutil.which("npm")
    if not npm:
        raise SystemExit("npm not found: install Node.js 20+ first")
    if not (FRONTEND / "node_modules").exists():
        subprocess.run([npm, "ci"], cwd=FRONTEND, check=True)
    subprocess.run([npm, "run", "build"], cwd=FRONTEND, check=True)


def cache_control(key: str) -> str:
    if key.startswith("assets/"):
        return IMMUTABLE
    if key == "index.html":
        return NO_CACHE
    return ONE_DAY


def write_local_config(outputs: dict) -> Path:
    """frontend/public/config.json for the Vite dev server (gitignored), from the same Terraform outputs
    that Terraform uses for the deployed one. Login works on localhost because http://localhost:5173 is an
    allowed callback/logout URL of the "spa" app client."""
    domain = outputs["auth_domain"]
    config = {
        "apiUrl": outputs["api_url"].rstrip("/"),
        "region": outputs["region"],
        "auth": {
            "authority": f"https://cognito-idp.{outputs['region']}.amazonaws.com/{outputs['user_pool_id']}",
            "userPoolId": outputs["user_pool_id"],
            "clientId": outputs["spa_client_id"],
            "domain": domain,
        },
    }
    path = FRONTEND / "public" / "config.json"
    path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    return path


def content_type(path: Path) -> str:
    return CONTENT_TYPES.get(path.suffix.lower()) or mimetypes.guess_type(path.name)[0] or "application/octet-stream"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--no-build", action="store_true", help="upload the existing dist/ without rebuilding")
    parser.add_argument("--local-config", action="store_true", help="only write frontend/public/config.json for local dev")
    args = parser.parse_args()

    outputs = load_outputs()
    if args.local_config:
        print(f"Wrote {write_local_config(outputs)}")
        return
    if not args.no_build:
        build()

    s3 = boto3.client("s3", region_name=outputs["region"])
    bucket = outputs["frontend_bucket"]
    files = sorted(p for p in DIST.rglob("*") if p.is_file() and p.relative_to(DIST).as_posix() not in SKIP)
    # Upload index.html LAST, so it never references assets that aren't uploaded yet.
    files.sort(key=lambda p: p.name == "index.html")
    for path in files:
        key = path.relative_to(DIST).as_posix()
        s3.upload_file(
            str(path),
            bucket,
            key,
            ExtraArgs={"ContentType": content_type(path), "CacheControl": cache_control(key)},
        )
        print(f"  uploaded {key:<70} {cache_control(key)}")

    cloudfront = boto3.client("cloudfront")
    invalidation = cloudfront.create_invalidation(
        DistributionId=outputs["frontend_distribution_id"],
        InvalidationBatch={
            "Paths": {"Quantity": 2, "Items": ["/index.html", "/config.json"]},
            "CallerReference": f"deploy-{int(time.time())}",
        },
    )["Invalidation"]
    print(f"\nUploaded {len(files)} files to s3://{bucket}; invalidation {invalidation['Id']} {invalidation['Status']}")
    print(f"Storefront: {outputs['frontend_url']}")


if __name__ == "__main__":
    main()
