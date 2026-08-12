"""
URL scoring service: extract features from a raw URL, run a tiered model, and
return a human-friendly verdict with confidence.

Tiers
-----
* "fast"  - 12 URL-only/DNS features, available for every URL immediately.
* "full"  - 23 features, adds page-HTML content signals once the page loads.

Both models are KNNImputer + RandomForest pipelines (see train_models.py).
Labels are 0 = phishing, 1 = legitimate.
"""

from __future__ import annotations

import os
import pickle
import threading
import time
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from networksecurity.utils.feature_extraction.extractor import (
    FEATURE_NAMES,
    PhishingFeatureExtractor,
)

MODEL_DIR = os.path.join("final_model")
MODEL_URL_PATH = os.path.join(MODEL_DIR, "model_url.pkl")
MODEL_FULL_PATH = os.path.join(MODEL_DIR, "model_full.pkl")

HTML_FEATURES = [
    "Favicon", "Request_URL", "URL_of_Anchor", "Links_in_tags", "SFH",
    "Submitting_to_email", "Redirect", "on_mouseover", "RightClick",
    "popUpWidnow", "Iframe",
]

LABELS = {0: "phishing", 1: "legitimate"}


class _TieredModel:
    """Lazily loads both model artifacts once."""

    def __init__(self) -> None:
        self._fast = None
        self._full = None

    def _load(self, path: str):
        with open(path, "rb") as f:
            return pickle.load(f)

    def fast(self):
        if self._fast is None:
            self._fast = self._load(MODEL_URL_PATH)
        return self._fast

    def full(self):
        if self._full is None:
            self._full = self._load(MODEL_FULL_PATH)
        return self._full


class UrlScorer:
    """Thread-safe scorer with an in-memory result cache."""

    def __init__(
        self,
        extractor: Optional[PhishingFeatureExtractor] = None,
        cache_ttl: float = 600.0,
        cache_size: int = 4096,
    ) -> None:
        self.extractor = extractor or PhishingFeatureExtractor()
        self.models = _TieredModel()
        self.cache_ttl = cache_ttl
        self._lock = threading.Lock()
        self._cache: Dict[str, tuple] = {}
        self._cache_size = cache_size

    # ------------------------------------------------------------- cache
    def _cached(self, url: str):
        with self._lock:
            entry = self._cache.get(url)
        if entry is None:
            return None
        ts, value = entry
        if time.time() - ts > self.cache_ttl:
            with self._lock:
                self._cache.pop(url, None)
            return None
        return value

    def _store(self, url: str, value: dict) -> None:
        with self._lock:
            if len(self._cache) >= self._cache_size:
                oldest = min(self._cache.items(), key=lambda kv: kv[1][0])[0]
                self._cache.pop(oldest, None)
            self._cache[url] = (time.time(), value)

    # ----------------------------------------------------------- scoring
    def _choose_tier(self, features: Dict[str, float]) -> str:
        html_present = sum(1 for f in HTML_FEATURES if not pd.isna(features.get(f)))
        return "full" if html_present >= 8 else "fast"

    def score(self, url: str) -> Dict:
        """Score a single URL. Returns a verdict dict."""
        url = url.strip()
        cached = self._cached(url)
        if cached is not None:
            return cached

        features = self.extractor.extract(url)
        tier = self._choose_tier(features)
        artifact = self.models.full() if tier == "full" else self.models.fast()
        feature_cols = artifact["features"]
        pipeline = artifact["pipeline"]

        row = {col: features.get(col, np.nan) for col in feature_cols}
        df = pd.DataFrame([row], columns=feature_cols)

        prediction = int(pipeline.predict(df)[0])
        probabilities = pipeline.predict_proba(df)[0]
        confidence = float(probabilities[prediction])
        phishing_probability = float(probabilities[0])

        if phishing_probability >= 0.6:
            risk = "high"
        elif phishing_probability >= 0.4:
            risk = "medium"
        else:
            risk = "low"

        result = {
            "url": url,
            "result": prediction,
            "label": LABELS.get(prediction, "unknown"),
            "confidence": round(confidence, 4),
            "phishing_probability": round(phishing_probability, 4),
            "risk": risk,
            "tier": tier,
            "features": {
                k: (None if pd.isna(v) else float(v)) for k, v in features.items()
            },
        }
        self._store(url, result)
        return result

    def score_many(self, urls: List[str]) -> List[Dict]:
        return [self.score(url) for url in urls]


def get_scorer() -> UrlScorer:
    """Module-level singleton so models load once per process."""
    global _SCORER
    if _SCORER is None:
        _SCORER = UrlScorer()
    return _SCORER


_SCORER: Optional[UrlScorer] = None
