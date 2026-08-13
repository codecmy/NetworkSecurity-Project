"""Tests for the S3 model store (manifest resolution, artifact download,
SHA-256 integrity verification). S3 is stubbed out; no real AWS calls."""

from __future__ import annotations

import hashlib
import io
import json
import os
from types import SimpleNamespace

import pytest
from botocore.exceptions import ClientError

from networksecurity.serving.model_store import S3ModelStore, ModelStoreError


class FakeNoSuchKey(ClientError):
    def __init__(self):
        super().__init__({"Error": {"Code": "NoSuchKey"}}, "GetObject")


class FakeS3:
    def __init__(self, objects: dict):
        self.exceptions = SimpleNamespace(NoSuchKey=FakeNoSuchKey)
        self.objects = objects
        self.downloaded = []

    def get_object(self, Bucket=None, Key=None, **kwargs):
        if Key not in self.objects:
            raise FakeNoSuchKey()
        return {"Body": io.BytesIO(self.objects[Key]), "ETag": '"etag-123"'}

    def head_object(self, Bucket=None, Key=None, **kwargs):
        if Key not in self.objects:
            raise ClientError({"Error": {"Code": "404"}}, "HeadObject")
        return {"ETag": '"e"'}

    def download_file(self, Bucket, Key, Filename, **kwargs):
        if Key not in self.objects:
            raise ClientError({"Error": {"Code": "404"}}, "GetObject")
        with open(Filename, "wb") as fh:
            fh.write(self.objects[Key])
        self.downloaded.append(Key)


def sha(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def build_store(objects: dict, **store_kwargs) -> S3ModelStore:
    store = S3ModelStore(bucket="test-bucket", **store_kwargs)
    store.s3 = FakeS3(objects)
    return store


def make_version_objects(version="v1", files=("model_url.pkl", "model_full.pkl")):
    content = {name: f"{name}-payload".encode() for name in files}
    metadata = {
        "version": version,
        "sha256": {name: sha(content[name]) for name in content},
        "metrics": {"accuracy": 0.9, "f1": 0.88, "precision": 0.87, "recall": 0.9},
    }
    objects = {
        f"models/{version}/{name}": content[name] for name in content
    }
    objects[f"models/{version}/metadata.json"] = json.dumps(metadata).encode()
    return objects


def test_version_returns_pinned_env(monkeypatch):
    objects = {
        "production/manifest.json": b'{"version": "v12"}',
        "models/v12/metadata.json": b'{"version": "v12"}',
    }
    monkeypatch.setenv("PHISHGUARD_MODEL_VERSION", "v9")
    store = build_store(objects)
    assert store.version() == "v9"


def test_version_falls_back_to_manifest(monkeypatch):
    monkeypatch.delenv("PHISHGUARD_MODEL_VERSION", raising=False)
    objects = {"production/manifest.json": b'{"version": "v12"}'}
    store = build_store(objects)
    assert store.version() == "v12"


def test_manifest_missing_raises():
    store = build_store({})
    with pytest.raises(ModelStoreError, match="not found"):
        store.production_manifest()


def test_manifest_invalid_json_raises():
    store = build_store({"production/manifest.json": b"not json"})
    with pytest.raises(ModelStoreError, match="not valid JSON"):
        store.production_manifest()


def test_manifest_without_version_raises():
    store = build_store({"production/manifest.json": b'{"model": "x"}'})
    with pytest.raises(ModelStoreError, match="version"):
        store.production_manifest()


def test_ensure_artifacts_downloads_and_verifies(tmp_path, monkeypatch):
    monkeypatch.delenv("PHISHGUARD_MODEL_VERSION", raising=False)
    objects = make_version_objects("v3")
    store = build_store(objects)
    local_dir = store.ensure_artifacts("v3", cache_dir=str(tmp_path))
    for name in ("model_url.pkl", "model_full.pkl"):
        path = os.path.join(local_dir, name)
        assert os.path.isfile(path)
        assert open(path, "rb").read() == objects[f"models/v3/{name}"]
    assert len(store.s3.downloaded) == 2


def test_ensure_artifacts_idempotent(tmp_path):
    objects = make_version_objects("v3")
    store = build_store(objects)
    store.ensure_artifacts("v3", cache_dir=str(tmp_path))
    before = list(store.s3.downloaded)
    store.ensure_artifacts("v3", cache_dir=str(tmp_path))
    assert store.s3.downloaded == before


def test_ensure_artifacts_hash_mismatch_fails_closed(tmp_path):
    objects = make_version_objects("v3")
    # Corrupt model_full.pkl but keep the recorded hash of the good payload.
    objects["models/v3/model_full.pkl"] = b"tampered"
    store = build_store(objects)
    with pytest.raises(ModelStoreError, match="SHA-256"):
        store.ensure_artifacts("v3", cache_dir=str(tmp_path))
    # The tampered artifact must not be left behind.
    assert not os.path.exists(os.path.join(str(tmp_path), "v3", "model_full.pkl"))


def test_ensure_artifacts_missing_metadata_raises(tmp_path):
    store = build_store({"models/v9/model_url.pkl": b"x"})
    with pytest.raises(ModelStoreError, match="metadata"):
        store.ensure_artifacts("v9", cache_dir=str(tmp_path))
