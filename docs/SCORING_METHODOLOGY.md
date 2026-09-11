# EDUNOVA AI — Scoring Methodology

## Placement probability (ML)
- Features: cgpa, attendance, backlogs, skill_count, avg_skill_level, project_count, internship_count, certification_count, hackathon_count
- Model: best of LR / RF / GB by ROC-AUC (see `ml/models/placement_meta.json`)
- Dataset: **synthetic educational** — not real hiring outcomes
- Explainability: feature contributions → positive/negative factors

## Intelligence Score (deterministic)
Weighted blend of dimensions (academic, technical, projects, experience, resume, career alignment, interview, certifications, learning, evidence strength). Each dimension exposes a how-calculated note in the UI/API.

## Skill confidence
Combines self-reported level with project/internship/certification/interview evidence signals. Labels: High / Medium / Low / Not evidenced.

## Opportunity / dream-company fit
Role–skill and company-requirement overlap scores with Strong / Competitive / Developing / Major gap buckets. Always labelled as **compatibility estimate**.

## What-if
Scenario simulation only — recalculates estimates without mutating the database; not a hiring forecast.

## Governance
Scoring lives in `app/services/*` — not in templates. Magic numbers should stay in service modules with comments.
