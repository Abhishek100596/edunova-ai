"""
Train placement classifiers on the SYNTHETIC educational CSV.

Runnable from Nexora_AI root:
    python -m ml.training.train_placement

Trains LogisticRegression, RandomForestClassifier, and GradientBoostingClassifier,
evaluates with hold-out + cross-validation metrics, picks the best by ROC-AUC,
and saves joblib + meta JSON under ml/models/.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.model_selection import cross_val_score, train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

ROOT = Path(__file__).resolve().parents[2]
CSV_PATH = ROOT / "ml" / "datasets" / "placement_synthetic.csv"
MODEL_PATH = ROOT / "ml" / "models" / "placement_model.joblib"
META_PATH = ROOT / "ml" / "models" / "placement_meta.json"

TARGET = "placed"
FEATURE_NAMES = [
    "cgpa",
    "attendance",
    "backlogs",
    "skill_count",
    "avg_skill_level",
    "project_count",
    "internship_count",
    "certification_count",
    "hackathon_count",
]


def _metrics(y_true, y_pred, y_proba) -> dict[str, float]:
    return {
        "accuracy": float(accuracy_score(y_true, y_pred)),
        "precision": float(precision_score(y_true, y_pred, zero_division=0)),
        "recall": float(recall_score(y_true, y_pred, zero_division=0)),
        "f1": float(f1_score(y_true, y_pred, zero_division=0)),
        "roc_auc": float(roc_auc_score(y_true, y_proba)),
    }


def _feature_importances(model, feature_names: list[str]) -> dict[str, float]:
    """Extract importances from tree models or |coef| from logistic pipelines."""
    est = model
    if hasattr(model, "named_steps"):
        # Pipeline: prefer final estimator
        est = model.named_steps.get("clf", model.steps[-1][1])

    if hasattr(est, "feature_importances_"):
        vals = np.asarray(est.feature_importances_, dtype=float)
    elif hasattr(est, "coef_"):
        vals = np.abs(np.asarray(est.coef_, dtype=float).ravel())
        total = vals.sum() or 1.0
        vals = vals / total
    else:
        vals = np.ones(len(feature_names), dtype=float) / len(feature_names)

    return {
        name: round(float(vals[i]), 6) if i < len(vals) else 0.0
        for i, name in enumerate(feature_names)
    }


def _build_candidates(seed: int = 42) -> dict[str, object]:
    return {
        "LogisticRegression": Pipeline(
            steps=[
                ("scaler", StandardScaler()),
                (
                    "clf",
                    LogisticRegression(
                        max_iter=2000,
                        class_weight="balanced",
                        random_state=seed,
                    ),
                ),
            ]
        ),
        "RandomForestClassifier": RandomForestClassifier(
            n_estimators=200,
            max_depth=8,
            min_samples_leaf=3,
            class_weight="balanced",
            random_state=seed,
            n_jobs=1,
        ),
        "GradientBoostingClassifier": GradientBoostingClassifier(
            n_estimators=150,
            learning_rate=0.08,
            max_depth=3,
            random_state=seed,
        ),
    }


def train(csv_path: Path = CSV_PATH) -> dict:
    if not csv_path.exists():
        raise FileNotFoundError(
            f"Dataset not found: {csv_path}\n"
            "Run: python ml/datasets/generate_dataset.py"
        )

    df = pd.read_csv(csv_path)
    missing = [c for c in FEATURE_NAMES + [TARGET] if c not in df.columns]
    if missing:
        raise ValueError(f"CSV missing columns: {missing}")

    X = df[FEATURE_NAMES]
    y = df[TARGET].astype(int)

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )

    results: dict[str, dict] = {}
    fitted: dict[str, object] = {}

    print("=" * 60)
    print("NEXORA placement training (SYNTHETIC dataset)")
    print(f"Rows: {len(df)} | Features: {len(FEATURE_NAMES)} | Train/Test: "
          f"{len(X_train)}/{len(X_test)}")
    print("=" * 60)

    for name, model in _build_candidates().items():
        model.fit(X_train, y_train)
        y_pred = model.predict(X_test)
        if hasattr(model, "predict_proba"):
            y_proba = model.predict_proba(X_test)[:, 1]
        else:
            y_proba = y_pred.astype(float)

        holdout = _metrics(y_test, y_pred, y_proba)
        cv_auc = cross_val_score(
            model, X, y, cv=5, scoring="roc_auc", n_jobs=1
        )
        cv_acc = cross_val_score(
            model, X, y, cv=5, scoring="accuracy", n_jobs=1
        )
        entry = {
            **holdout,
            "cv_roc_auc_mean": float(cv_auc.mean()),
            "cv_roc_auc_std": float(cv_auc.std()),
            "cv_accuracy_mean": float(cv_acc.mean()),
            "cv_accuracy_std": float(cv_acc.std()),
        }
        results[name] = entry
        fitted[name] = model
        print(f"\n{name}")
        for k, v in entry.items():
            print(f"  {k}: {v:.4f}")

    best_name = max(results.keys(), key=lambda n: results[n]["roc_auc"])
    best_model = fitted[best_name]
    # Refit on full data for deployment artifact.
    best_model.fit(X, y)

    importances = _feature_importances(best_model, FEATURE_NAMES)
    trained_at = datetime.now(timezone.utc).isoformat()

    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(best_model, MODEL_PATH)

    meta = {
        "algorithm": best_name,
        "metrics": results[best_name],
        "all_algorithms": results,
        "feature_names": FEATURE_NAMES,
        "trained_at": trained_at,
        "feature_importances": importances,
        "dataset": str(csv_path.name),
        "n_rows": int(len(df)),
        "synthetic": True,
        "note": "Trained on SYNTHETIC educational data only.",
    }
    META_PATH.write_text(json.dumps(meta, indent=2), encoding="utf-8")

    print("\n" + "=" * 60)
    print(f"Best algorithm (by hold-out roc_auc): {best_name}")
    print(f"Saved model → {MODEL_PATH}")
    print(f"Saved meta  → {META_PATH}")
    print("=" * 60)
    return meta


def main() -> None:
    train()


if __name__ == "__main__":
    main()
