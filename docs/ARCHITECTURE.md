# EDUNOVA AI Architecture

Folder: `Nexora_AI/` (legacy path; product brand is **EDUNOVA AI**).

```
Browser (Jinja + nexora.css / edunova.css + Chart.js)
        ↓
Flask routes (main / auth / student / intelligence / admin / api)
        ↓
Services
  placement · career · skill_gap · skill_confidence · intelligence_score
  company_intel · evidence · comparison · what_if · career_switch
  jd_intel · roadmap · resume_intel · interview · coach
        ↓
   ┌────┴────┐
   ML layer   AI provider layer
   (joblib)   (local | gemini | openai)
        ↓
SQLAlchemy / SQLite (DATABASE_URL supported)
  + research models: Company, EvidenceSource, CompanyRoleRequirement, …
```

## Auth flow
Register → hash password → StudentProfile → onboarding → dashboard

## Placement prediction flow
Profile features → joblib model (or deterministic fallback) → probability + readiness + factors → PredictionRecord  
**Dataset is synthetic/educational — not real hiring outcomes.**

## Evidence / company intelligence
Curated Company + EvidenceSource + role requirements → opportunity fit / dream company (compatibility estimates)

## Career / skill-gap flow
StudentSkill vs RoleSkill → weighted match % → skill gap matrix (priority + evidence labels) → roadmap

## Resume / JD flow
Upload PDF/DOCX → extract → keywords → completeness; paste JD → structured extract + profile compare

## Interview / coach
Question bank + heuristic or LLM evaluation; coach uses stored profile context only (no invented achievements)

## Security
CSRF, Flask-Login, role checks, upload validation, env secrets, student data isolation

## Separation
Independent from Nexus AI (Android). No shared runtime or packaging.
