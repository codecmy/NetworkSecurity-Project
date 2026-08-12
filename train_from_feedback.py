"""
Fold user feedback from the NetworkSecurityFeedback database into the training
dataset.

Semantics of a "wrong" rating:
  * verdict high/medium + feedback=wrong  -> user says the page is legitimate
  * verdict low          + feedback=wrong  -> user says the page is phishing

Rows whose features were stored at feedback time are used directly; rows
without features fall back to a fresh extraction (best-effort).

Produces real_data/features_with_feedback.csv and prints a summary. Running the
retraining itself stays a separate step (see train_models_real.py).

Usage:
    python train_from_feedback.py [--output real_data/features_with_feedback.csv]
"""

import argparse
import os

import pandas as pd

from networksecurity.database import feedback_repository
from networksecurity.utils.feature_extraction.extractor import (
    FEATURE_NAMES,
    PhishingFeatureExtractor,
)

BASE_DATA = os.path.join("real_data", "features.csv")
LABEL_MAP = {"phishing": 0, "legitimate": 1}


def corrected_label(doc) -> str:
    """Map a 'wrong' rating to the corrected ground-truth label."""
    verdict = (doc.get("verdict") or "").strip().lower()
    return "legitimate" if verdict in ("high", "medium") else "phishing"


def build_feedback_rows(extractor, limit: int) -> pd.DataFrame:
    docs = feedback_repository.load_feedback(limit=limit)
    rows = []
    for doc in docs:
        if doc.get("feedback") != "wrong":
            continue
        url = doc.get("url", "").strip()
        if not url:
            continue
        label = corrected_label(doc)
        features = doc.get("features") or {}
        missing = [f for f in FEATURE_NAMES if f not in features]
        if missing:
            try:
                features = {**extractor.extract(url)}
            except Exception:
                continue
        if not all(f in features for f in FEATURE_NAMES):
            continue
        row = {"url": url, "label": label, **{f: features.get(f) for f in FEATURE_NAMES}}
        row["_source"] = "feedback"
        rows.append(row)
    return pd.DataFrame(rows)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default=os.path.join("real_data", "features_with_feedback.csv"))
    parser.add_argument("--limit", type=int, default=0, help="Max feedback docs to pull (0 = all)")
    args = parser.parse_args()

    total = feedback_repository.count_feedback()
    print(f"feedback docs in DB: {total}")

    extractor = PhishingFeatureExtractor(request_timeout=6.0, resolve_timeout=4.0, use_whois=False)
    fb = build_feedback_rows(extractor, args.limit)
    print(f"usable 'wrong' feedback rows: {len(fb)}")
    if fb.empty:
        print("nothing to merge yet — collect feedback via the extension first.")
        return

    base = pd.read_csv(BASE_DATA)
    print(f"base real-data rows: {len(base)}")

    known = set(base["url"].str.strip().str.lower())
    fb["_keep"] = ~fb["url"].str.strip().str.lower().isin(known)
    new_rows = fb[fb["_keep"]].drop(columns=["_keep", "_source"]).reset_index(drop=True)
    print(f"new rows from feedback (not already in base data): {len(new_rows)}")
    if new_rows.empty:
        return

    merged = pd.concat([base, new_rows], ignore_index=True)
    merged.to_csv(args.output, index=False)
    print(f"wrote {len(merged)} rows -> {args.output}")
    print("To retrain on this merged set later:")
    print("  python train_models_real.py  # (after pointing DATA_PATH at the merged file)")


if __name__ == "__main__":
    main()
