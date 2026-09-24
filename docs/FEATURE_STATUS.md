# EduNova AI — Feature Status

Last updated after browser/Render reliability repair (resume skills render, interview one-at-a-time UX, form error surfacing, coach timeout fallback, `/api/health` + Render `healthCheckPath`, AI `normalize_ai_response`, expanded error handlers).

| Feature | Status | Implementation | AI / Deterministic / Hybrid | Persistence | Fallback | Tests |
|---------|--------|----------------|----------------------------|-------------|----------|-------|
| Authentication | Working | Flask-Login + hashed passwords | Deterministic | SQL users | N/A | Yes |
| Dashboard | Working | personalization + Career Snapshot | Hybrid metrics (det) | SQL | N/A | Yes |
| Placement prediction | Working | sklearn + logistic fallback | Deterministic / ML | prediction_records | Coefficient fallback | Yes |
| Explainability | Working | ml/explainability | Deterministic | N/A | Fallback model | Partial |
| Career matching | Working | career.score_role / match_roles | Deterministic | Catalog SQL | Empty catalog → empty list | Yes |
| Skill gap | Working | skill_gap service | Deterministic | SQL skills | N/A | Yes |
| Roadmap | Working | roadmap stages + progress persistence | Hybrid (gaps deterministic) | learning_roadmaps/tasks | Template stages | Yes |
| Learning planner | Working | learning_planner + Learning Hub UI | Hybrid | Ephemeral plan (+ roadmap DB) | Weeks without AI | Yes |
| Resume analysis | Working | resume_intel heuristics + safe PDF/DOCX errors | Deterministic | resumes/analyses | Friendly ValueError | Yes |
| JD analyzer | Working | jd_intel + readable template + AI explain | Hybrid | Ephemeral | Fit panel only | Yes |
| AI Coach | Working | coach + Groq/OpenAI/Gemini/local | Hybrid | ai_conversations | Local coach + timeout catch | Yes |
| Mock Interview | Working | interview service; one editable question in UI | Hybrid (AI eval when configured) | interview_* tables | Rule-based eval | Yes |
| Interview Results | Working | session_detail + followup | Hybrid | SQL | Local summary | Yes |
| Project mentor | Working | project_mentor + Projects UI | Hybrid | projects.analysis_json | Evidence-only | Yes |
| Company intelligence | Working | company_intel | Deterministic | companies/requirements | Disclaimer | Yes |
| Dream Company | Working | dream_company_analysis | Deterministic | SQL | Error payload | Yes |
| Opportunity Fit | Working | opportunity_fit | Deterministic | SQL | Empty list | Yes |
| Career Switch | Working | career_switch | Deterministic | N/A | Disclaimer | Yes |
| What-If | Working | what_if + readable UI + AI explain (non-mutating) | Hybrid | None | Numbers only | Yes |
| Analytics | Working | charts from SQL | Deterministic | progress/predictions | Empty charts | Partial |
| PDF Report | Working | ReportLab route | Deterministic | Generated on demand | N/A | Partial |
| Projects / GitHub | Working | github_project service | Deterministic analysis | projects.analysis_json | Manual add | Yes |
| Notifications | Working | Notification model | Deterministic | notifications | N/A | Partial |
| Admin | Working | admin blueprint | Deterministic | Catalog SQL | Auth gate | Yes |
| Admin health | Working | healthcheck service | Deterministic | N/A | Soft fails per check | Yes |
| Public `/api/health` | Working | DB + AI config status (no secrets) | Deterministic | N/A | Soft AI/ML fields | Yes |
| Company Comparison UI | Working | comparison + HTML cards | Deterministic | N/A | Error card | Yes |
| Career Comparison UI | Working | comparison + HTML cards | Deterministic | N/A | Error card | Yes |

## Provider matrix

| Provider | Config | Secret | Notes |
|----------|--------|--------|-------|
| local | `AI_PROVIDER=local` | none | Always available |
| groq | `AI_PROVIDER=groq` | `GROQ_API_KEY` or `AI_API_KEY` | Official SDK + HTTP; model via `GROQ_MODEL`/`AI_MODEL` (default `openai/gpt-oss-120b`) |
| openai | `AI_PROVIDER=openai` | `AI_API_KEY` | Chat Completions |
| gemini | `AI_PROVIDER=gemini` | `AI_API_KEY` | Gemini generateContent |

`DEMO_MODE` does not force local AI. Fallback order: configured primary → other configured clouds (without misusing Groq keys as OpenAI) → local. Coach catches provider exceptions and continues with local guidance.

## Acceptance checklist (college demo)

- [x] App starts; DB creates tables; demo seed when empty + DEMO_MODE
- [x] Register / Login / Logout
- [x] Dashboard, careers, placement, roadmap, interview, resume, coach pages load
- [x] Coach uses student context + history; normalizes non-natural responses
- [x] Groq selected when `AI_PROVIDER=groq` even if `DEMO_MODE=true`
- [x] Roadmap includes Foundation → … → Interview → Job Applications
- [x] Resume skills list (JSON strings) renders without 500
- [x] Interview shows one unanswered question form at a time
- [x] What-If does not mutate profile
- [x] `requirements.txt` includes `groq`
- [x] Render: `Procfile`, `render.yaml` (`healthCheckPath: /api/health`), `runtime.txt`, production `FLASK_DEBUG=false`
- [x] Automated tests: `pytest -q` (71 passed, 1 skipped)
