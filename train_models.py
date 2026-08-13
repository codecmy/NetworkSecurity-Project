"""
Train the production URL-scoring models used by the extension API.

Unlike the original full-30-feature model, these are trained only on features
the real-time extractor can compute:

  * model_url.pkl  (12 features) - URL-only + DNS. Available immediately for
    every URL, no lookups beyond DNS/SSL.
  * model_full.pkl (23 features) - adds page-HTML content features. Used once
    the page has been fetched and parsed.

Both exclude WHOIS/paid-feed features (Alexa rank, PageRank, Google index,
backlinks, statistical blacklists) which are unavailable at prediction time.

Usage:
    python train_models.py
"""

import os
import sys

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import KNNImputer
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.metrics import accuracy_score, f1_score, precision_score, recall_score

from networksecurity.exception.exception import NetworkSecurityException

URL_FEATURES = [
    "having_IP_Address", "URL_Length", "Shortining_Service", "having_At_Symbol",
    "double_slash_redirecting", "Prefix_Suffix", "having_Sub_Domain",
    "SSLfinal_State", "port", "HTTPS_token", "Abnormal_URL",
]
DNS_FEATURES = ["DNSRecord"]
HTML_FEATURES = [
    "Favicon", "Request_URL", "URL_of_Anchor", "Links_in_tags", "SFH",
    "Submitting_to_email", "Redirect", "on_mouseover", "RightClick",
    "popUpWidnow", "Iframe",
]

MODELS = {
    "model_url.pkl": URL_FEATURES + DNS_FEATURES,
    "model_full.pkl": URL_FEATURES + DNS_FEATURES + HTML_FEATURES,
}

SAVE_DIR = "final_model"
DATA_PATH = os.path.join("Network_Data", "phisingData.csv")


def build_pipeline():
    return Pipeline(
        [
            ("impute", KNNImputer(n_neighbors=3, weights="uniform")),
            ("clf", RandomForestClassifier(n_estimators=200, n_jobs=-1)),
        ]
    )


def main():
    try:
        df = pd.read_csv(DATA_PATH)
        df["Result"] = df["Result"].replace(-1, 0)  # 0=phishing, 1=legitimate

        train_df, test_df = train_test_split(df, test_size=0.2, random_state=42)

        os.makedirs(SAVE_DIR, exist_ok=True)
        per_model = {}
        for filename, features in MODELS.items():
            pipeline = build_pipeline()
            pipeline.fit(train_df[features], train_df["Result"])
            y_pred = pipeline.predict(test_df[features])
            metrics = {
                "accuracy": round(accuracy_score(test_df["Result"], y_pred), 4),
                "f1": round(f1_score(test_df["Result"], y_pred), 4),
                "precision": round(precision_score(test_df["Result"], y_pred), 4),
                "recall": round(recall_score(test_df["Result"], y_pred), 4),
            }
            print(
                f"{filename:18s} acc={metrics['accuracy']:.4f} "
                f"f1={metrics['f1']:.4f} "
                f"prec={metrics['precision']:.4f} "
                f"rec={metrics['recall']:.4f}"
            )
            with open(os.path.join(SAVE_DIR, filename), "wb") as f:
                import pickle

                pickle.dump({"features": features, "pipeline": pipeline}, f)
            per_model[filename] = metrics
            print(f"  saved -> {os.path.join(SAVE_DIR, filename)}")

        # Write metrics.json consumed by aws/scripts/package_model.py.
        # Top-level metrics reflect the full-tier model (model_full.pkl).
        import json

        full_metrics = per_model["model_full.pkl"]
        metrics_json = {
            **full_metrics,
            "models": per_model,
            "trained_from": DATA_PATH,
        }
        with open(os.path.join("metrics.json"), "w", encoding="utf-8") as f:
            json.dump(metrics_json, f, indent=2)
        print("wrote -> metrics.json (used by aws/scripts/package_model.py)")
    except Exception as e:
        raise NetworkSecurityException(e, sys) from e


if __name__ == "__main__":
    main()
