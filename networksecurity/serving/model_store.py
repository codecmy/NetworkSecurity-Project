"""S3-backed model registry access for the Lambda inference runtime.

The production manifest (``production/manifest.json``) is the source of truth
for which immutable model version is live. Artifacts are downloaded once per
execution environment during cold start and verified against the SHA-256
recorded in the version metadata before they are deserialised. The model is
never downloaded from S3 on the per-request inference path.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
from typing import Dict, List, Optional

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger("networksecurity.serving")

MANIFEST_KEY = os.getenv("PHISHGUARD_MANIFEST_KEY", "production/manifest.json")
MODELS_PREFIX = "models"
REQUIRED_ARTIFACTS = ("model_url.pkl", "model_full.pkl")
OPTIONAL_ARTIFACTS = ("preprocessor.pkl",)
ARTIFACT_KEYS = REQUIRED_ARTIFACTS + OPTIONAL_ARTIFACTS

DEFAULT_CACHE_DIR = os.getenv(
    "PHISHGUARD_MODEL_CACHE_DIR",
    os.path.join(os.sep, "tmp", "phishguard-models"),
)


class ModelStoreError(RuntimeError):
    """Raised when the model registry cannot be read safely."""


class S3ModelStore:
    """Reads the production manifest and stages model artifacts locally."""

    def __init__(
        self,
        bucket: str,
        region: Optional[str] = None,
        manifest_key: str = MANIFEST_KEY,
    ) -> None:
        self.bucket = bucket
        self.manifest_key = manifest_key
        self.s3 = boto3.client("s3", region_name=region)
        self._lock = threading.Lock()
        self._manifest: Optional[dict] = None
        self._manifest_etag: Optional[str] = None
        self._ready: set = set()

    # ------------------------------------------------------------ manifest
    def production_manifest(self, force: bool = False) -> dict:
        """Return the current production manifest (cached in memory)."""
        with self._lock:
            if self._manifest is not None and not force:
                return self._manifest
        obj = self._get_object(self.manifest_key, required=True)
        try:
            manifest = json.loads(obj["Body"].read().decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as exc:
            raise ModelStoreError(
                f"production manifest {self.manifest_key} is not valid JSON: {exc}"
            ) from exc
        if not manifest.get("version"):
            raise ModelStoreError(
                f"production manifest {self.manifest_key} has no 'version'"
            )
        with self._lock:
            self._manifest = manifest
            self._manifest_etag = obj.get("ETag")
        return manifest

    def version(self) -> str:
        """The version this environment should serve.

        An explicitly pinned version (PHISHGUARD_MODEL_VERSION) always wins;
        otherwise the production manifest is the source of truth.
        """
        pinned = os.getenv("PHISHGUARD_MODEL_VERSION", "").strip()
        if pinned:
            return pinned
        return self.production_manifest()["version"]

    # ------------------------------------------------------------ artifacts
    def ensure_artifacts(
        self,
        version: str,
        cache_dir: Optional[str] = None,
    ) -> str:
        """Download + verify the artifacts for ``version`` into a local dir.

        Returns the local directory. Idempotent within an execution
        environment: already-verified artifacts are reused across invocations.
        """
        base_dir = cache_dir or DEFAULT_CACHE_DIR
        local_dir = os.path.join(base_dir, version)

        with self._lock:
            if version in self._ready and os.path.isdir(local_dir):
                return local_dir

        metadata = self._version_metadata(version)
        expected = {k: v for k, v in (metadata.get("sha256") or {}).items()}

        missing_required = [
            key for key in REQUIRED_ARTIFACTS if not self._key_exists(version, key)
        ]
        if missing_required:
            raise ModelStoreError(
                f"version {version} is missing required artifacts: {missing_required}"
            )

        present = [
            key
            for key in REQUIRED_ARTIFACTS + OPTIONAL_ARTIFACTS
            if self._key_exists(version, key)
        ]

        os.makedirs(local_dir, exist_ok=True)
        for key in present:
            local_path = os.path.join(local_dir, key)
            remote_key = f"{MODELS_PREFIX}/{version}/{key}"
            expected_sha = expected.get(key)
            if os.path.isfile(local_path) and self._verify(local_path, expected_sha):
                continue
            self._download_and_verify(remote_key, local_path, expected_sha)

        with self._lock:
            self._ready.add(version)
        return local_dir

    # --------------------------------------------------------------- helpers
    def _get_object(self, key: str, required: bool):
        try:
            return self.s3.get_object(Bucket=self.bucket, Key=key)
        except self.s3.exceptions.NoSuchKey:
            if required:
                raise ModelStoreError(
                    f"{key} not found in bucket {self.bucket}"
                ) from None
            return None
        except Exception as exc:
            raise ModelStoreError(f"failed to read s3://{self.bucket}/{key}: {exc}") from exc

    def _key_exists(self, version: str, filename: str) -> bool:
        key = f"{MODELS_PREFIX}/{version}/{filename}"
        try:
            self.s3.head_object(Bucket=self.bucket, Key=key)
            return True
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") in ("404", "NotFound"):
                return False
            raise ModelStoreError(
                f"failed to inspect s3://{self.bucket}/{key}: {exc}"
            ) from exc

    def _version_metadata(self, version: str) -> dict:
        key = f"{MODELS_PREFIX}/{version}/metadata.json"
        obj = self._get_object(key, required=True)
        try:
            return json.loads(obj["Body"].read().decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as exc:
            raise ModelStoreError(
                f"metadata for {version} ({key}) is not valid JSON: {exc}"
            ) from exc

    def _download_and_verify(self, remote_key: str, local_path: str, expected_sha: Optional[str]) -> None:
        try:
            self.s3.download_file(self.bucket, remote_key, local_path)
        except Exception as exc:
            raise ModelStoreError(
                f"failed to download s3://{self.bucket}/{remote_key}: {exc}"
            ) from exc
        if not self._verify(local_path, expected_sha):
            try:
                os.remove(local_path)
            except OSError:
                pass
            raise ModelStoreError(
                f"artifact s3://{self.bucket}/{remote_key} failed SHA-256 verification; refusing to load"
            )

    @staticmethod
    def _verify(path: str, expected_sha: Optional[str]) -> bool:
        if not expected_sha:
            return True
        digest = hashlib.sha256()
        with open(path, "rb") as fh:
            for chunk in iter(lambda: fh.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest() == str(expected_sha).lower()


def artifact_keys() -> List[str]:
    return list(ARTIFACT_KEYS)


def manifest_keys() -> Dict[str, str]:
    """Human-meaningful registry keys for documentation/ops tooling."""
    return {
        "manifest": MANIFEST_KEY,
        "history": "production/manifest-history",
        "models": MODELS_PREFIX,
    }
