"""Tests for the Lambda handler (routes, validation, API key, CORS, errors).
The model runtime and S3 store are stubbed; no real AWS or network calls."""

from __future__ import annotations

import importlib.util
import json
import os
from types import SimpleNamespace

import pytest

from networksecurity.database import feedback_repository


HANDLER_PATH = os.path.join(os.path.dirname(__file__), "..", "aws", "lambda", "handler.py")


@pytest.fixture()
def handler():
    spec = importlib.util.spec_from_file_location("handler_under_test", HANDLER_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    fake_scorer = SimpleNamespace(
        score=lambda url: {
            "url": url,
            "result": 0,
            "label": "phishing",
            "confidence": 0.91,
            "phishing_probability": 0.91,
            "risk": "high",
            "tier": "full",
            "features": {"having_IP_Address": 1.0},
        },
        score_many=lambda urls: [
            {
                "url": u,
                "result": 0,
                "label": "phishing",
                "confidence": 0.91,
                "phishing_probability": 0.91,
                "risk": "high",
                "tier": "full",
                "features": {},
            }
            for u in urls
        ],
    )
    fake_runtime = SimpleNamespace(
        version="v12",
        _store=SimpleNamespace(
            production_manifest=lambda: {
                "version": "v12",
                "model": "models/v12/model_url.pkl",
                "model_full": "models/v12/model_full.pkl",
                "accuracy": 0.94,
                "precision": 0.93,
                "recall": 0.95,
                "f1": 0.94,
                "metrics": {"accuracy": 0.94},
            }
        ),
        get=lambda: (fake_scorer, "v12"),
    )
    module._runtime = lambda: fake_runtime
    module._COLD_START = True
    module._REQUEST_ID = "test-request"
    return module


def invoke(handler, method, path, body=None, headers=None, context=None):
    event = {
        "rawPath": path,
        "requestContext": {"http": {"method": method}},
        "headers": headers or {},
    }
    if body is not None:
        event["body"] = json.dumps(body)
    return handler.lambda_handler(event, context)


def test_health(handler):
    resp = invoke(handler, "GET", "/health")
    assert resp["statusCode"] == 200
    assert json.loads(resp["body"])["status"] == "ok"


def test_predict_url_single(handler):
    resp = invoke(handler, "POST", "/predict_url", {"url": "http://example.com"})
    assert resp["statusCode"] == 200
    payload = json.loads(resp["body"])
    assert payload["label"] == "phishing"
    assert payload["risk"] == "high"
    assert payload["model_version"] == "v12"


def test_api_v1_analyze_alias(handler):
    resp = invoke(handler, "POST", "/api/v1/analyze", {"url": "http://example.com"})
    assert resp["statusCode"] == 200
    assert json.loads(resp["body"])["tier"] == "full"


def test_predict_urls_batch(handler):
    resp = invoke(
        handler,
        "POST",
        "/predict_urls",
        {"urls": ["http://a.com", "http://b.com"]},
    )
    assert resp["statusCode"] == 200
    assert len(json.loads(resp["body"])["results"]) == 2


def test_invalid_input_returns_400(handler):
    resp = invoke(handler, "POST", "/predict_url", {"url": "x"})
    assert resp["statusCode"] == 400
    resp = invoke(handler, "POST", "/predict_urls", {"urls": []})
    assert resp["statusCode"] == 400


def test_api_key_required(handler, monkeypatch):
    monkeypatch.setenv("PHISHGUARD_API_KEY", "secret")
    resp = invoke(handler, "POST", "/predict_url", {"url": "http://example.com"})
    assert resp["statusCode"] == 401
    resp = invoke(
        handler,
        "POST",
        "/predict_url",
        {"url": "http://example.com"},
        headers={"x-api-key": "secret"},
    )
    assert resp["statusCode"] == 200


def test_version_endpoint(handler):
    resp = invoke(handler, "GET", "/api/v1/model/version")
    assert resp["statusCode"] == 200
    payload = json.loads(resp["body"])
    assert payload["version"] == "v12"
    assert payload["accuracy"] == 0.94


def test_options_returns_cors(handler):
    resp = invoke(handler, "OPTIONS", "/predict_url")
    assert resp["statusCode"] == 200
    assert resp["headers"]["Access-Control-Allow-Origin"] == "*"


def test_unknown_path_returns_404(handler):
    resp = invoke(handler, "GET", "/nope")
    assert resp["statusCode"] == 404


def test_feedback_dropped_when_mongo_unavailable(handler, monkeypatch):
    class FakeExtractor:
        def extract(self, url):
            return {"having_IP_Address": 1.0}

    handler._feedback_extractor = FakeExtractor()

    def boom(doc):
        raise RuntimeError("mongo down")

    monkeypatch.setattr(feedback_repository, "save_feedback", boom)
    resp = invoke(
        handler,
        "POST",
        "/feedback",
        {
            "url": "http://example.com",
            "verdict": "high",
            "label": "phishing",
            "feedback": "wrong",
        },
    )
    assert resp["statusCode"] == 200
    assert json.loads(resp["body"])["source"] == "dropped"


def test_inference_failure_returns_502(handler):
    def boom(url):
        raise RuntimeError("model corrupted")

    fake_scorer = SimpleNamespace(score=boom, score_many=lambda u: u)
    fake_runtime = SimpleNamespace(get=lambda: (fake_scorer, "v12"))
    handler._runtime = lambda: fake_runtime

    resp = invoke(handler, "POST", "/predict_url", {"url": "http://example.com"})
    assert resp["statusCode"] == 502
