"""Simple feature-contribution explanations for the placement model."""

from __future__ import annotations

from typing import Any, Mapping, Sequence

import numpy as np


def _as_array(
    feature_vector: Mapping[str, float] | Sequence[float],
    feature_names: Sequence[str] | None = None,
) -> tuple[np.ndarray, list[str]]:
    if isinstance(feature_vector, Mapping):
        names = list(feature_names) if feature_names else list(feature_vector.keys())
        values = np.array([float(feature_vector.get(n, 0.0)) for n in names], dtype=float)
        return values, names
    values = np.asarray(feature_vector, dtype=float).ravel()
    if feature_names is None:
        names = [f"f{i}" for i in range(len(values))]
    else:
        names = list(feature_names)
        if len(names) != len(values):
            raise ValueError(
                f"feature_names length {len(names)} != vector length {len(values)}"
            )
    return values, names


def _importances(model, n_features: int) -> np.ndarray:
    est = model
    if hasattr(model, "named_steps"):
        est = model.named_steps.get("clf", model.steps[-1][1])

    if hasattr(est, "feature_importances_"):
        imp = np.asarray(est.feature_importances_, dtype=float).ravel()
    elif hasattr(est, "coef_"):
        imp = np.abs(np.asarray(est.coef_, dtype=float).ravel())
        total = imp.sum() or 1.0
        imp = imp / total
    else:
        imp = np.ones(n_features, dtype=float) / max(1, n_features)

    if len(imp) < n_features:
        imp = np.pad(imp, (0, n_features - len(imp)))
    return imp[:n_features]


def explain_prediction(
    feature_vector: Mapping[str, float] | Sequence[float],
    model,
    *,
    feature_names: Sequence[str] | None = None,
    feature_means: Mapping[str, float] | Sequence[float] | None = None,
    top_k: int | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """
    Return positive/negative contribution lists.

    Contribution ≈ feature_importances_ * (value - mean).
    If means are omitted, mean defaults to 0 (contribution ≈ importance * value).
    """
    values, names = _as_array(feature_vector, feature_names)
    imp = _importances(model, len(values))

    if feature_means is None:
        means = np.zeros(len(values), dtype=float)
    elif isinstance(feature_means, Mapping):
        means = np.array([float(feature_means.get(n, 0.0)) for n in names], dtype=float)
    else:
        means = np.asarray(feature_means, dtype=float).ravel()
        if len(means) != len(values):
            raise ValueError("feature_means length mismatch")

    deltas = values - means
    contributions = imp * deltas

    items: list[dict[str, Any]] = []
    for i, name in enumerate(names):
        items.append(
            {
                "feature": name,
                "value": round(float(values[i]), 4),
                "mean": round(float(means[i]), 4),
                "importance": round(float(imp[i]), 6),
                "contribution": round(float(contributions[i]), 6),
            }
        )

    positive = sorted(
        [x for x in items if x["contribution"] >= 0],
        key=lambda x: -x["contribution"],
    )
    negative = sorted(
        [x for x in items if x["contribution"] < 0],
        key=lambda x: x["contribution"],
    )

    if top_k is not None:
        k = max(0, int(top_k))
        positive = positive[:k]
        negative = negative[:k]

    return {"positive": positive, "negative": negative}


def explain(
    feature_vector: Mapping[str, float] | Sequence[float],
    model,
    **kwargs: Any,
) -> dict[str, list[dict[str, Any]]]:
    """Alias for explain_prediction."""
    return explain_prediction(feature_vector, model, **kwargs)
