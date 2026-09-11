# Data Dictionary (core tables)

| Table | Field | Meaning |
|-------|-------|---------|
| users | email | Login identity |
| users | password_hash | Werkzeug hash |
| users | role | student \| admin |
| student_profiles | cgpa | Academic score |
| student_profiles | onboarding_pct | 0–100 completion |
| student_skills | level | 1–5 proficiency |
| career_roles | name | Target role title |
| role_skills | required_level | Needed proficiency |
| role_skills | importance | Weight in match score |
| prediction_records | probability | Stored ML estimate |
| resumes | stored_filename | Safe upload name |
| interview_answers | score | AI-assisted score |
| learning_tasks | status | not_started \| in_progress \| completed |
| evidence_sources | verification_status | verified / needs_review / stale / unverified |
| evidence_sources | url | Provenance URL (no fabricated links) |
| companies | company_type | product / service / other |
| companies | careers_url | Official careers portal when known |
| company_role_requirements | skill + level + evidence_source_id | Role-level requirement with optional evidence FK |
| learning_resources | last_verified_at | Resource freshness |
| user_targets | company/role prefs | Dream / target selections |

See SQLAlchemy models under `app/models/` (including `research.py`) for full schema.
