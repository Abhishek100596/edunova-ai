"""Load the trained placement model and print evaluation metrics from meta JSON."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import joblib
import pandas as pd
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)

ROOT = Path(__file__).resolve().parents[2]
MODEL_PATH = ROOT / "ml" / "models" / "placement_model.joblib"
META_PATH = ROOT / "ml" / "models" / "placement_meta.json"
CSV_PATH = ROOT / "ml" / "datasets" / "placement_synthetic.csv"
TARGET = "placed"


def load_model(model_path: Path = MODEL_PATH):
    if not model_path.exists():
        raise FileNotFoundError(f"Model not found: {model_path}")
    return joblib.load(model_path)


def load_meta(meta_path: Path = META_PATH) -> dict[str, Any]:
    if not meta_path.exists():
        raise FileNotFoundError(f"Meta not found: {meta_path}")
    return json.loads(meta_path.read_text(encoding="utf-8"))


def print_metrics(meta: dict[str, Any] | None = None) -> dict[str, Any]:
    """Print stored training metrics (and optionally re-score the CSV)."""
    meta = meta or load_meta()
    print("=" * 60)
    print("NEXORA placement model evaluation")
    print(f"Algorithm : {meta.get('algorithm')}")
    print(f"Trained at: {meta.get('trained_at')}")
    print(f"Dataset   : {meta.get('dataset')} (synthetic={meta.get('synthetic')})")
    print("-" * 60)
    metrics = meta.get("metrics") or {}
    for key, value in metrics.items():
        if isinstance(value, float):
            print(f"  {key}: {value:.4f}")
        else:
            print(f"  {key}: {value}")
    importances = meta.get("feature_importances") or {}
    if importances:
        print("-" * 60)
        print("Feature importances:")
        for name, val in sorted(importances.items(), key=lambda kv: -kv[1]):
            print(f"  {name}: {val:.4f}")
    print("=" * 60)
    return meta


def evaluate_on_csv(
    model_path: Path = MODEL_PATH,
    csv_path: Path = CSV_PATH,
    meta_path: Path = META_PATH,
) -> dict[str, float]:
    """Re-evaluate the saved model on the synthetic CSV and print a report."""
    model = load_model(model_path)
    meta = load_meta(meta_path) if meta_path.exists() else {}
    feature_names = meta.get("feature_names")
    df = pd.read_csv(csv_path)
    if not feature_names:
        feature_names = [c for c in df.columns if c != TARGET]
    X = df[feature_names]
    y = df[TARGET].astype(int)
    y_pred = model.predict(X)
    y_proba = (
        model.predict_proba(X)[:, 1]
        if hasattr(model, "predict_proba")
        else y_pred.astype(float)
    )
    scores = {
        "accuracy": float(accuracy_score(y, y_pred)),
        "precision": float(precision_score(y, y_pred, zero_division=0)),
        "recall": float(recall_score(y, y_pred, zero_division=0)),
        "f1": float(f1_score(y, y_pred, zero_division=0)),
        "roc_auc": float(roc_auc_score(y, y_proba)),
    }
    print_metrics(meta)
    print("\nFull-dataset re-score:")
    for k, v in scores.items():
        print(f"  {k}: {v:.4f}")
    print("\nClassification report:")
    print(classification_report(y, y_pred, digits=4))
    return scores


def main() -> None:
    evaluate_on_csv()


if __name__ == "__main__":
    main()
