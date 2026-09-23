# EDUNOVA AI

**AI-Powered Education, Skill & Career Intelligence**  
Crafted by Shivendra Pratap Singh

> Know where you are. Know what you need. Build what comes next.

Standalone Flask platform for personalized career, skill, and evidence-based readiness intelligence.

**This repository is independent from Nexus AI (Android).** Do not merge the projects.

## Features

- Auth (student/admin), CSRF, hashed passwords
- Rich demo profile + personalization engine + **AI Career Snapshot**
- 75+ skills, 100+ companies, 20+ career roles, role roadmaps
- Placement prediction (synthetic educational ML) + explainability
- Skill intelligence / confidence, skill-gap matrix
- Company intelligence, opportunity fit, dream company
- Resume Intelligence with ATS-style heuristics
- JD Analyzer with readable fit panels + optional AI learning priorities
- Mock interview with role-specific banks + AI/heuristic evaluation
- AI Career Coach (HTML + `/api/coach`) with Groq primary + local fallback
- Learning hub with **4-week AI learning planner** (gap-grounded)
- Project mentor grounded in GitHub/manual project evidence
- Analytics Lab, What-If (non-mutating), career/company compare, PDF report
- Admin catalog tools + **demo health check** (no secrets exposed)

EduNova combines **deterministic intelligence**, **ML**, and **generative AI** — LLMs explain and coach; they do not silently replace scores.

See `docs/AI_FEATURE_REGISTRY.md` for the full AI/ML feature map.

## Technology stack

- Python 3.11+
- Flask + Flask-Login + Flask-WTF + Flask-SQLAlchemy
- SQLite (local) / PostgreSQL (Render via `DATABASE_URL`)
- scikit-learn educational placement model
- Gunicorn
- Optional Groq / Gemini / OpenAI for coach narratives and interview evaluation

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
| `AI_PROVIDER` | `local` \| `gemini` \| `openai` \| `groq` |
| `AI_API_KEY` | Server-side only — Groq key when `AI_PROVIDER=groq`, else Gemini/OpenAI |
| `AI_MODEL` | Model id (Groq default `openai/gpt-oss-120b`) |
| `GROQ_API_KEY` | Optional dedicated Groq key (preferred locally) |
| `GROQ_MODEL` | Optional dedicated Groq model override |
| `PORT` / `HOST` | Runtime bind (Render sets `PORT`) |
| `SESSION_COOKIE_SECURE` | `true` behind HTTPS |
| `FLASK_DEBUG` | Must be `false` in production |

### AI provider examples

Local (no cloud key required):

```bash
AI_PROVIDER=local
```

Groq (recommended production — either style works):

```bash
AI_PROVIDER=groq
AI_API_KEY=your_groq_key
AI_MODEL=openai/gpt-oss-120b
```

or:

```bash
AI_PROVIDER=groq
GROQ_API_KEY=your_groq_key
GROQ_MODEL=openai/gpt-oss-120b
```

`DEMO_MODE=true` seeds demo catalog data only — it does **not** disable Groq.
If the cloud provider fails, EduNova falls back safely to local coaching.
The app still starts without any AI key.

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

Required env vars: `SECRET_KEY`, `DATABASE_URL` (Postgres recommended), `FLASK_DEBUG=false`, `SESSION_COOKIE_SECURE=true`.

Optional AI: `AI_PROVIDER=groq`, `GROQ_API_KEY` (set in Render dashboard), `GROQ_MODEL`, or `AI_API_KEY` / `AI_MODEL` for Gemini/OpenAI. `DEMO_MODE` optional.

## Architecture

- `app/routes/` — HTTP blueprints
- `app/services/` — career/skill/coach/roadmap/interview logic
- `app/ai/` — providers (local, Gemini, OpenAI, Groq) + response normalization
- `ml/` — educational placement model
- `scripts/` — idempotent demo seed
- `docs/FEATURE_STATUS.md` — feature matrix

## AI architecture

| Layer | Notes |
|-------|-------|
| ML | Placement estimate from synthetic educational dataset |
| Deterministic | Readiness, skill gap, company fit, what-if, resume heuristics, roadmap progress |
| External AI | Coach, interview evaluation/summary when API key configured |
| Fallback | Local/rule-based keeps demos working offline |

## Limitations

- Scores are estimates, not hiring guarantees
- Company catalog is educational
- Resume analysis is heuristic, not a vendor ATS claim

## License / academic use

Portfolio / academic project.
