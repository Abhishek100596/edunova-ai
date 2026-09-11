# EDUNOVA AI

**AI-Powered Education, Skill & Career Intelligence**  
Crafted by Shivendra Pratap Singh

> Know where you are. Know what you need. Build what comes next.

Standalone Flask platform for personalized career, skill, and evidence-based readiness intelligence.

**This repository is independent from Nexus AI (Android).** Do not merge the projects.

## Features

- Auth (student/admin), CSRF, hashed passwords
- Rich demo profile + personalization engine
- 75+ skills, 100+ companies, 20+ career roles, role roadmaps
- Placement prediction (synthetic educational ML) + explainability
- Skill intelligence / confidence, skill-gap matrix
- Company intelligence, opportunity fit, dream company
- Resume Intelligence with ATS-style heuristics
- Mock interview with role-specific banks + local scoring
- AI Career Coach (HTML + `/api/coach`) with cloud provider + deterministic local fallback
- Analytics Lab, What-If, career/company compare, PDF report

## Technology stack

- Python 3.11+
- Flask + Flask-Login + Flask-WTF + Flask-SQLAlchemy
- SQLite (local) / PostgreSQL (Render via `DATABASE_URL`)
- scikit-learn educational placement model
- Gunicorn
- Optional Gemini / OpenAI for coach narratives

## Local setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python ml/datasets/generate_dataset.py
python -m ml.training.train_placement
python scripts/seed_demo_data.py
python run.py
```

Open http://127.0.0.1:5000

With `DEMO_MODE=true`, an empty database is also auto-seeded on first app boot (skipped under pytest).

### Demo accounts

| Role | Email | Password |
|------|-------|----------|
| Student | demo@edunova.ai | Demo@123 |
| Admin | admin@edunova.ai | Admin@123 |

Legacy aliases `demo@nexora.ai` / `admin@nexora.ai` still work.

## Environment

Copy `.env.example`. Variables used by the app:

| Variable | Purpose |
|----------|---------|
| `SECRET_KEY` | Flask secret |
| `DATABASE_URL` | SQLite default or Postgres URL |
| `DEMO_MODE` | Auto-seed empty DB + demo-friendly defaults |
| `AI_PROVIDER` | `local` \| `gemini` \| `openai` |
| `AI_API_KEY` | Server-side only |
| `AI_MODEL` | Optional model name |
| `PORT` / `HOST` | Runtime bind (Render sets `PORT`) |
| `SESSION_COOKIE_SECURE` | `true` behind HTTPS |
| `FLASK_DEBUG` | Must be `false` in production |

Never commit real API keys.

## Testing

```bash
pytest -q
```

## Render deployment

Set **Root Directory** to this repository root (not a nested Nexus folder).

**Build Command**

```bash
pip install -r requirements.txt && python ml/datasets/generate_dataset.py && python -m ml.training.train_placement && python scripts/seed_demo_data.py
```

**Start Command**

```bash
gunicorn run:app --bind 0.0.0.0:$PORT --workers 2 --timeout 120
```

Equivalent files: `Procfile`, `render.yaml`, `runtime.txt`, `wsgi.py`.

Required env vars: `SECRET_KEY`, `DATABASE_URL` (Postgres recommended), `FLASK_DEBUG=false`, `SESSION_COOKIE_SECURE=true`. Optional: `AI_PROVIDER`, `AI_API_KEY`, `AI_MODEL`, `DEMO_MODE`.

## Architecture

- `app/routes/` — HTTP blueprints
- `app/services/` — career/skill/coach/roadmap logic
- `app/ai/` — AI providers (local fallback + cloud)
- `ml/` — educational placement model
- `scripts/` — idempotent demo seed

## AI architecture

| Layer | Notes |
|-------|-------|
| ML | Placement estimate from synthetic educational dataset |
| Deterministic | Readiness, skill gap, company fit, what-if, resume heuristics |
| External AI | Coach / optional interview narrative when API key configured |
| Fallback | LocalProvider keeps demos working offline |

## Limitations

- Scores are estimates, not hiring guarantees
- Company catalog is educational
- Resume analysis is heuristic, not a vendor ATS claim

## License / academic use

Portfolio / academic project.
