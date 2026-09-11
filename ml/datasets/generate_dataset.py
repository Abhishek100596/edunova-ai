#!/usr/bin/env python3
"""
Generate a SYNTHETIC educational placement dataset for NEXORA AI.

IMPORTANT — THIS DATA IS ENTIRELY SYNTHETIC.
It is fabricated for teaching, demos, and offline model training only.
It does NOT represent real students, colleges, employers, or placement outcomes.
Do not use it for real admissions, hiring, or high-stakes decisions.

Output: ml/datasets/placement_synthetic.csv (~800 rows)
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

FEATURE_COLUMNS = [
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

TARGET_COLUMN = "placed"
N_ROWS = 800
RANDOM_SEED = 42

OUT_PATH = Path(__file__).resolve().parent / "placement_synthetic.csv"


def _placement_probability(row: dict[str, float]) -> float:
    """Deterministic logistic-style probability for synthetic labels."""
    # Map raw features into a bounded score (tuned for ~45–55% positive rate).
    cgpa_n = row["cgpa"] / 10.0
    att_n = row["attendance"] / 100.0
    backlog_pen = 1.0 - min(row["backlogs"], 5) * 0.18
    skill_n = min(row["skill_count"] / 12.0, 1.0)
    level_n = row["avg_skill_level"] / 5.0
    proj_n = min(row["project_count"] / 4.0, 1.0)
    intern_n = min(row["internship_count"] / 2.0, 1.0)
    cert_n = min(row["certification_count"] / 3.0, 1.0)
    hack_n = min(row["hackathon_count"] / 3.0, 1.0)

    z = (
        -3.8
        + 1.55 * cgpa_n
        + 0.65 * att_n
        + 0.85 * backlog_pen
        + 1.05 * skill_n
        + 1.15 * level_n
        + 1.00 * proj_n
        + 1.10 * intern_n
        + 0.60 * cert_n
        + 0.50 * hack_n
    )
    z = max(-20.0, min(20.0, z))
    return 1.0 / (1.0 + np.exp(-z))


def generate_synthetic_rows(n: int = N_ROWS, seed: int = RANDOM_SEED) -> pd.DataFrame:
    """
    Create n SYNTHETIC student rows with correlated placement labels.

    All values are simulated with NumPy RNG — no real student data.
    """
    rng = np.random.default_rng(seed)

    # Broader spread so both placed and not-placed classes appear.
    cgpa = np.clip(rng.normal(6.8, 1.4, n), 4.0, 10.0)
    attendance = np.clip(rng.normal(78.0, 12.0, n), 40.0, 100.0)
    backlogs = rng.choice([0, 1, 2, 3, 4, 5], size=n, p=[0.40, 0.22, 0.16, 0.12, 0.07, 0.03])
    skill_count = rng.integers(1, 14, size=n)
    avg_skill_level = np.clip(rng.normal(2.9, 1.0, n), 1.0, 5.0)
    project_count = rng.integers(0, 7, size=n)
    internship_count = rng.choice([0, 1, 2, 3], size=n, p=[0.45, 0.35, 0.15, 0.05])
    certification_count = rng.integers(0, 6, size=n)
    hackathon_count = rng.integers(0, 5, size=n)

    rows: list[dict[str, float | int]] = []
    for i in range(n):
        row = {
            "cgpa": round(float(cgpa[i]), 2),
            "attendance": round(float(attendance[i]), 1),
            "backlogs": int(backlogs[i]),
            "skill_count": int(skill_count[i]),
            "avg_skill_level": round(float(avg_skill_level[i]), 2),
            "project_count": int(project_count[i]),
            "internship_count": int(internship_count[i]),
            "certification_count": int(certification_count[i]),
            "hackathon_count": int(hackathon_count[i]),
        }
        p = _placement_probability(row)
        # Bernoulli draw — labels are stochastic around the logistic curve.
        placed = 1 if rng.random() < p else 0
        row[TARGET_COLUMN] = placed
        rows.append(row)

    df = pd.DataFrame(rows, columns=FEATURE_COLUMNS + [TARGET_COLUMN])
    # Guarantee both classes exist for stratified train/test splits.
    if df[TARGET_COLUMN].nunique() < 2:
        flip_idx = int(rng.integers(0, n))
        df.loc[flip_idx, TARGET_COLUMN] = 1 - int(df.loc[flip_idx, TARGET_COLUMN])
    return df


def main() -> None:
    print(
        "Generating SYNTHETIC educational placement dataset "
        f"({N_ROWS} rows). Not real student data."
    )
    df = generate_synthetic_rows()
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT_PATH, index=False)
    placed_rate = df[TARGET_COLUMN].mean()
    print(f"Wrote {len(df)} rows → {OUT_PATH}")
    print(f"Class balance placed=1: {placed_rate:.1%}")
    print("Columns:", ", ".join(df.columns))


if __name__ == "__main__":
    main()
