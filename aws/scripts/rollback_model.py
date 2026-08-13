"""Roll production back to a previously promoted model version.

Model artifacts are immutable, so rollback is a manifest pointer flip: the
promotion record preserved in ``production/manifest-history/<version>.json``
is re-applied as the production manifest. No retraining is involved.

Usage:
    python aws/scripts/rollback_model.py \\
        --bucket networksecurity-model-registry \\
        --version v12 \\
        --region us-east-1
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import sys
from typing import List

import boto3
from botocore.exceptions import ClientError

MANIFEST_KEY = "production/manifest.json"
MANIFEST_HISTORY_PREFIX = "production/manifest-history"
MODELS_PREFIX = "models"


def utc_now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_args(argv: List[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bucket", required=True)
    parser.add_argument("--version", required=True, help="version to roll back to, e.g. v12")
    parser.add_argument("--region", default=os.getenv("AWS_REGION", "us-east-1"))
    parser.add_argument("--force", action="store_true",
                        help="rewrite the manifest even if production already points at this version")
    return parser.parse_args(argv)


def main(argv: List[str]) -> int:
    args = parse_args(argv)
    s3 = boto3.client("s3", region_name=args.region)

    history_key = f"{MANIFEST_HISTORY_PREFIX}/{args.version}.json"
    try:
        obj = s3.get_object(Bucket=args.bucket, Key=history_key)
        rollback_manifest = json.loads(obj["Body"].read().decode("utf-8"))
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") == "NoSuchKey":
            print(f"error: no promotion record for {args.version} at "
                  f"s3://{args.bucket}/{history_key}", file=sys.stderr)
            return 1
        raise
    except (ValueError, UnicodeDecodeError) as exc:
        print(f"error: promotion record {history_key} is not valid JSON: {exc}",
              file=sys.stderr)
        return 1

    artifact_key = f"{MODELS_PREFIX}/{args.version}/model_url.pkl"
    try:
        s3.head_object(Bucket=args.bucket, Key=artifact_key)
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") in ("404", "NotFound"):
            print(f"error: artifacts for {args.version} are missing - cannot roll back",
                  file=sys.stderr)
            return 1
        raise

    current_etag = None
    try:
        current = s3.get_object(Bucket=args.bucket, Key=MANIFEST_KEY)
        current_etag = current.get("ETag")
        current_manifest = json.loads(current["Body"].read().decode("utf-8"))
        if current_manifest.get("version") == args.version and not args.force:
            print(f"production already points at {args.version}; nothing to do "
                  "(use --force to rewrite)")
            return 0
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") != "NoSuchKey":
            raise

    rollback_manifest = dict(rollback_manifest)
    rollback_manifest["promoted_at"] = utc_now()
    rollback_manifest["rolled_back_to"] = args.version

    put_kwargs: dict = {
        "Bucket": args.bucket,
        "Key": MANIFEST_KEY,
        "Body": json.dumps(rollback_manifest, indent=2).encode("utf-8"),
        "ContentType": "application/json",
    }
    if current_etag:
        put_kwargs["IfMatch"] = current_etag
    try:
        s3.put_object(**put_kwargs)
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") == "PreconditionFailed":
            print("error: production manifest changed during rollback; re-run",
                  file=sys.stderr)
            return 1
        raise

    print(f"rolled production back to {args.version} (s3://{args.bucket}/{MANIFEST_KEY})")
    print("then redeploy Lambda with that version, e.g. deploy-lambda.yml "
          f"model_version={args.version}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
