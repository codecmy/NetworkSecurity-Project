"""Evaluate a candidate model version against production and promote on pass.

Reads the candidate ``metadata.json`` (written by ``package_model.py``) from
S3, compares it against the current production manifest and only promotes when
the candidate satisfies the promotion policy:

    candidate metric >= min_accuracy          (default 0.6, matches the
                                              MODEL_TRAINER_EXPECTED_SCORE
                                              constant in the training pipeline)
    candidate metric >= production metric + improve_by

A candidate is never deployed merely because training completed: a failed
comparison exits non-zero and leaves production untouched.

Promotion flips the production manifest pointer to the immutable candidate.
The previous manifest is preserved under ``production/manifest-history/`` for
rollback, and the manifest write is guarded with a conditional S3 put
(If-Match on the current ETag) so two concurrent promotions cannot silently
clobber each other.

Usage:
    python aws/scripts/publish_model.py \\
        --bucket networksecurity-model-registry \\
        --version v13 \\
        --region us-east-1
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import sys
from typing import List, Optional

import boto3
from botocore.exceptions import ClientError

MANIFEST_KEY = "production/manifest.json"
MANIFEST_HISTORY_PREFIX = "production/manifest-history"
MODELS_PREFIX = "models"


def utc_now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def read_s3_json(s3, bucket: str, key: str):
    obj = s3.get_object(Bucket=bucket, Key=key)
    return json.loads(obj["Body"].read().decode("utf-8"))


def parse_args(argv: List[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bucket", required=True)
    parser.add_argument("--version", required=True, help="candidate version, e.g. v13")
    parser.add_argument("--region", default=os.getenv("AWS_REGION", "us-east-1"))
    parser.add_argument("--min-accuracy", type=float, default=0.6,
                        help="minimum acceptable score (default: 0.6)")
    parser.add_argument("--improve-by", type=float, default=0.0,
                        help="candidate must exceed production by this much")
    parser.add_argument("--metric", default="accuracy",
                        choices=["accuracy", "f1", "precision", "recall"])
    parser.add_argument("--force", action="store_true",
                        help="bypass the evaluation criteria")
    return parser.parse_args(argv)


def main(argv: List[str]) -> int:
    args = parse_args(argv)
    s3 = boto3.client("s3", region_name=args.region)

    candidate_key = f"{MODELS_PREFIX}/{args.version}/metadata.json"
    try:
        candidate = read_s3_json(s3, args.bucket, candidate_key)
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") == "NoSuchKey":
            print(f"reject: candidate metadata not found at s3://{args.bucket}/{candidate_key}",
                  file=sys.stderr)
            return 1
        raise

    production = None
    production_etag = None
    try:
        production_obj = s3.get_object(Bucket=args.bucket, Key=MANIFEST_KEY)
        production = json.loads(production_obj["Body"].read().decode("utf-8"))
        production_etag = production_obj.get("ETag")
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") != "NoSuchKey":
            raise

    candidate_metrics = candidate.get("metrics") or {}
    cand_score = candidate_metrics.get(args.metric)
    if cand_score is None:
        print(f"reject: candidate {args.version} has no metric '{args.metric}'",
              file=sys.stderr)
        return 1

    prod_score = None
    if production:
        prod_score = (production.get("metrics") or {}).get(args.metric)
        if prod_score is None:
            prod_score = production.get(args.metric)

    prod_label = production.get("version") if production else "(none)"
    print(f"candidate {args.version}: {args.metric}={cand_score:.4f}")
    print(f"production {prod_label}: {args.metric}="
          + (f"{prod_score:.4f}" if prod_score is not None else "n/a"))

    passes = cand_score >= args.min_accuracy
    if prod_score is not None:
        passes = passes and cand_score >= prod_score + args.improve_by
    if not passes and not args.force:
        print(f"reject: candidate does not satisfy the promotion criteria "
              f"(min {args.metric} {args.min_accuracy:g}, must beat production by {args.improve_by:g})",
              file=sys.stderr)
        return 1
    if args.force:
        print("note: --force bypasses the promotion criteria")

    manifest = {
        "version": args.version,
        "model": f"{MODELS_PREFIX}/{args.version}/model_url.pkl",
        "model_full": f"{MODELS_PREFIX}/{args.version}/model_full.pkl",
        "preprocessor": f"{MODELS_PREFIX}/{args.version}/preprocessor.pkl",
        "sha256": candidate.get("sha256") or {},
        "metrics": candidate_metrics,
        "trained_at": candidate.get("trained_at"),
        "trained_from": candidate.get("trained_from"),
        "git_sha": candidate.get("git_sha"),
        "promoted_at": utc_now(),
    }
    for metric in ("accuracy", "precision", "recall", "f1"):
        if metric in candidate_metrics:
            manifest[metric] = candidate_metrics[metric]
    manifest["created_at"] = candidate.get("trained_at") or manifest["promoted_at"]

    history_key = f"{MANIFEST_HISTORY_PREFIX}/{args.version}.json"
    s3.put_object(
        Bucket=args.bucket,
        Key=history_key,
        Body=json.dumps(manifest, indent=2).encode("utf-8"),
        ContentType="application/json",
    )
    print(f"preserved promotion record: s3://{args.bucket}/{history_key}")

    put_kwargs: dict = {
        "Bucket": args.bucket,
        "Key": MANIFEST_KEY,
        "Body": json.dumps(manifest, indent=2).encode("utf-8"),
        "ContentType": "application/json",
    }
    if production_etag:
        put_kwargs["IfMatch"] = production_etag
    try:
        s3.put_object(**put_kwargs)
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") == "PreconditionFailed":
            print("reject: production manifest changed during promotion; re-run",
                  file=sys.stderr)
            return 1
        raise

    print(f"promoted {args.version} -> production (s3://{args.bucket}/{MANIFEST_KEY})")
    print("next step: deploy to Lambda, e.g. .github/workflows/deploy-lambda.yml "
          f"with model_version={args.version}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
