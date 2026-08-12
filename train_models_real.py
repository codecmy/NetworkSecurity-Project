"""
Train tiered models on REAL extracted URL features (from collect_real_data.py)
and compare them against the CSV-trained models on a held-out real test set.

Produces final_model/model_{url,full}_real.pkl; promote them to the live
filenames only if they win the comparison.

Usage:
    python train_models_real.py [--min-per-class 50]
"""

import argparse
import os
import pickle

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import KNNImputer
from sklearn.model_selection import StratifiedShuffleSplit, cross_val_score
from sklearn.pipeline import Pipeline
from sklearn.metrics import accuracy_score, f1_score, precision_score, recall_score

from networksecurity.utils.feature_extraction.extractor import FEATURE_NAMES

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
DATA_PATH = os.path.join("real_data", "features.csv")
LABEL_MAP = {"phishing": 0, "legitimate": 1}


def load_data():
    df = pd.read_csv(DATA_PATH)
    df["label"] = df["label"].str.strip().str.lower().map(LABEL_MAP)
    df = df.dropna(subset=["label"])
    df = df.dropna(subset=URL_FEATURES, thresh=len(URL_FEATURES) - 2)
    df["label"] = df["label"].astype(int)
    return df


def build_pipeline():
    return Pipeline(
        [
            ("impute", KNNImputer(n_neighbors=3, weights="uniform")),
            ("clf", RandomForestClassifier(n_estimators=300, n_jobs=-1, min_samples_leaf=2)),
        ]
    )


def evaluate(name, pipeline, X, y):
    acc = accuracy_score(y, pipeline.predict(X))
    f1 = f1_score(y, pipeline.predict(X))
    prec = precision_score(y, pipeline.predict(X))
    rec = recall_score(y, pipeline.predict(X))
    print(f"  {name:16s} acc={acc:.4f} f1={f1:.4f} prec={prec:.4f} rec={rec:.4f}")
    return acc, f1, prec, rec


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--min-per-class", type=int, default=40)
    args = parser.parse_args()

    df = load_data()
    print(f"real data: {len(df)} rows | {df['label'].value_counts().to_dict()}")

    min_count = min(df["label"].value_counts().to_dict().values())
    if min_count < args.min_per_class:
        print(f"too few real samples per class ({min_count}) - collecting more first")
        return

    y = df["label"].to_numpy()
    split = StratifiedShuffleSplit(n_splits=1, test_size=0.25, random_state=42)
    train_idx, test_idx = next(split.split(df, y))
    train, test = df.iloc[train_idx], df.iloc[test_idx]

    print(f"train: {len(train)}  test: {len(test)}")

    for filename, features in MODELS.items():
        print(f"\n=== {filename} ===")
        pipeline = build_pipeline()
        pipeline.fit(train[features], train["label"])
        with open(os.path.join(SAVE_DIR, filename.replace(".pkl", "_real.pkl")), "wb") as f:
            pickle.dump({"features": features, "pipeline": pipeline}, f)

        cv = cross_val_score(pipeline, train[features], train["label"], cv=5, scoring="f1")
        print(f"  5-fold CV F1 on train: {cv.mean():.4f} (+/- {cv.std():.4f})")
        evaluate("real-model (test)", pipeline, test[features], test["label"])

        # Compare against the CSV-trained live model on the same real test set
        live_path = os.path.join(SAVE_DIR, filename)
        if os.path.exists(live_path):
            with open(live_path, "rb") as f:
                live = pickle.load(f)
            evaluate("csv-model  (test)", live["pipeline"], test[features], test["label"])

    print("\nDone. To deploy the real models, overwrite model_url.pkl / model_full.pkl "
          "with their *_real.pkl counterparts.")


if __name__ == "__main__":
    main()
