"""Tests for the URL scoring service (real tiered models, stubbed extractor)."""

import pytest

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


def test_score_shape_and_labels():
    scorer = UrlScorer(extractor=_ZeroExtractor(), cache_ttl=0)
    result = scorer.score("http://example.com")
    assert set(result) == {
        "url", "result", "label", "confidence", "phishing_probability",
        "risk", "tier", "features",
    }
    assert result["url"] == "http://example.com"
    assert result["label"] in ("phishing", "legitimate")
    assert 0.0 <= result["confidence"] <= 1.0
    assert 0.0 <= result["phishing_probability"] <= 1.0
    assert result["tier"] in ("fast", "full")
    assert len(result["features"]) == 30


def test_score_all_zero_features_is_phishing():
    scorer = UrlScorer(extractor=_ZeroExtractor(), cache_ttl=0)
    result = scorer.score("http://example.com")
    # No HTML features present -> fast tier, and zero vector scores as phishing
    assert result["tier"] == "fast"
    assert result["result"] == 0
    assert result["label"] == "phishing"


def test_score_many():
    scorer = UrlScorer(extractor=_ZeroExtractor(), cache_ttl=0)
    results = scorer.score_many(["http://a.example", "http://b.example"])
    assert len(results) == 2
    assert all(r["result"] == 0 for r in results)
