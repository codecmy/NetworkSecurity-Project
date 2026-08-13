"""Package trained model artifacts into an immutable S3 model version.

Uploads local model files into ``s3://<bucket>/models/<version>/`` together
with a ``metadata.json`` recording SHA-256 hashes, file sizes and the metrics
from the training pipeline. This step never touches the production manifest;
promotion is a separate, explicit step (``publish_model.py``).

Version numbers are immutable ``vN`` prefixes derived from the highest existing
version (or forced with ``--version``). Existing versions are never overwritten.

Usage:
    python aws/scripts/package_model.py \\
        --bucket networksecurity-model-registry \\
        --models-dir final_model \\
        --metrics-json metrics.json \\
        --trained-at 2026-08-12T00:00:00Z \\
        --trained-from Network_Data/phisingData.csv \\
        --region us-east-1
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from typing import Dict, List

import boto3

MODELS_PREFIX = "models"
DEFAULT_FILES = ["model_url.pkl", "model_full.pkl", "preprocessor.pkl"]
METRICS_FIELDS = ("accuracy", "f1", "precision", "recall")


def sha256(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def next_version(s3, bucket: str) -> str:
    highest = 0
    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix=MODELS_PREFIX + "/", Delimiter="/"):
        for common in page.get("CommonPrefixes", []):
            name = common["Prefix"].rstrip("/").split("/")[-1]
            if name.startswith("v") and name[1:].isdigit():
                highest = max(highest, int(name[1:]))
    return f"v{highest + 1}"


def parse_args(argv: List[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bucket", required=True, help="S3 model registry bucket")
    parser.add_argument("--region", default=os.getenv("AWS_REGION", "us-east-1"))
    parser.add_argument("--models-dir", default="final_model")
    parser.add_argument(
        "--files",
        nargs="*",
        default=DEFAULT_FILES,
        help="model files to upload (default: %(default)s)",
    )
    parser.add_argument(
        "--metrics-json",
        required=True,
        help="metrics file from the training pipeline "
        "(keys: accuracy, f1, precision, recall)",
    )
    parser.add_argument(
        "--version",
        default=None,
        help="explicit immutable version, e.g. v13 (default: next vN)",
    )
    parser.add_argument("--trained-at", default=None)
    parser.add_argument("--trained-from", default=None)
    parser.add_argument("--git-sha", default=None)
    return parser.parse_args(argv)


def main(argv: List[str]) -> int:
    args = parse_args(argv)

    with open(args.metrics_json, "r", encoding="utf-8") as fh:
        metrics = json.load(fh)
    for metric in METRICS_FIELDS:
        if metric not in metrics:
            print(f"error: {args.metrics_json} is missing '{metric}'", file=sys.stderr)
            return 2

    files: Dict[str, str] = {}
    for name in args.files:
        path = os.path.join(args.models_dir, name)
        if os.path.isfile(path):
            files[name] = path
        else:
            print(f"note: {path} not found - skipping")
    if not files:
        print("error: no model files found to upload", file=sys.stderr)
        return 2

    s3 = boto3.client("s3", region_name=args.region)
    version = args.version or next_version(s3, args.bucket)

    sha_map = {name: sha256(path) for name, path in files.items()}
    size_map = {name: os.path.getsize(path) for name, path in files.items()}

    metadata = {
        "version": version,
        "artifacts": {name: f"{MODELS_PREFIX}/{version}/{name}" for name in files},
        "sha256": sha_map,
        "model_size_bytes": size_map,
        "metrics": metrics,
        "trained_at": args.trained_at,
        "trained_from": args.trained_from,
        "git_sha": args.git_sha,
    }

    for name, path in files.items():
        key = f"{MODELS_PREFIX}/{version}/{name}"
        s3.upload_file(path, args.bucket, key)
        print(f"uploaded s3://{args.bucket}/{key} ({size_map[name]} bytes, sha256={sha_map[name][:12]}...)")

    metadata_key = f"{MODELS_PREFIX}/{version}/metadata.json"
    s3.put_object(
        Bucket=args.bucket,
        Key=metadata_key,
        Body=json.dumps(metadata, indent=2).encode("utf-8"),
        ContentType="application/json",
    )
    print(f"wrote s3://{args.bucket}/{metadata_key}")
    print(f"package complete: s3://{args.bucket}/{MODELS_PREFIX}/{version}/")
    print("next step: evaluate + promote with aws/scripts/publish_model.py")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
