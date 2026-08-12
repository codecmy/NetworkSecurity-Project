"""Endpoint tests via FastAPI TestClient (in-process), with a stubbed extractor."""

import pytest
from fastapi.testclient import TestClient

import app as app_module
from networksecurity.utils.feature_extraction.extractor import FEATURE_NAMES
from networksecurity.utils.feature_extraction.scorer import UrlScorer


class _ZeroExtractor:
    HTML_FEATURES = [
        "Favicon", "Request_URL", "URL_of_Anchor", "Links_in_tags", "SFH",
        "Submitting_to_email", "Redirect", "on_mouseover", "RightClick",
        "popUpWidnow", "Iframe",
    ]

    def extract(self, url):
        features = {name: 0.0 for name in FEATURE_NAMES}
        for name in self.HTML_FEATURES:
            features[name] = float("nan")
        return features

    def extract_dataframe(self, urls):
        import pandas as pd

        return pd.DataFrame([self.extract(u) for u in urls], columns=FEATURE_NAMES)


@pytest.fixture(scope="module")
def client():
    scorer = UrlScorer(extractor=_ZeroExtractor(), cache_ttl=0)
    app_module.get_scorer = lambda: scorer
    return TestClient(app_module.app)


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_predict_url_schema_validation(client):
    response = client.post("/predict_url", json={"url": ""})
    assert response.status_code == 422


def test_predict_url_returns_verdict(client):
    response = client.post("/predict_url", json={"url": "http://example.com"})
    assert response.status_code == 200
    body = response.json()
    assert body["label"] in ("phishing", "legitimate")
    assert "confidence" in body
    assert len(body["features"]) == 30


def test_predict_urls_batch(client):
    response = client.post(
        "/predict_urls", json={"urls": ["http://example.com", "http://bit.ly/abc123"]}
    )
    assert response.status_code == 200
    results = response.json()["results"]
    assert len(results) == 2
    assert results[0]["result"] == 0  # zeros -> phishing


def test_rate_limit_429(client):
    for _ in range(200):
        client.post("/predict_url", json={"url": "http://example.com"})
    response = client.post("/predict_url", json={"url": "http://example.com"})
    assert response.status_code == 429
