# EduNova AI — Feature Status

Last updated after Groq / Coach / Interview / Roadmap hardening.

| Feature | Status | Implementation | AI / Deterministic / Hybrid | Persistence | Fallback | Tests |
|---------|--------|----------------|----------------------------|-------------|----------|-------|
| Authentication | Working | Flask-Login + hashed passwords | Deterministic | SQL users | N/A | Yes |
| Dashboard | Working | personalization service | Hybrid (metrics deterministic) | SQL | N/A | Partial |
| Placement prediction | Working | sklearn + logistic fallback | Deterministic / ML | prediction_records | Coefficient fallback | Yes |
| Explainability | Working | ml/explainability | Deterministic | N/A | Fallback model | Partial |
| Career matching | Working | career.score_role | Deterministic | Catalog SQL | Empty catalog → empty list | Yes |
| Skill gap | Working | skill_gap service | Deterministic | SQL skills | N/A | Yes |
| Roadmap | Working | roadmap service + stages | Hybrid (gaps deterministic; optional AI narrative later) | learning_roadmaps/tasks | Template stages | Yes |
| Resume analysis | Working | resume_intel heuristics | Deterministic | resumes/analyses | N/A | Partial |
| JD analyzer | Working | jd_intel | Deterministic | JD rows | N/A | Partial |
| AI Coach | Working | coach + providers | Hybrid | ai_conversations | Local coach | Yes |
| Mock Interview | Working | interview service | Hybrid (AI eval primary when configured) | interview_* tables | Rule-based eval | Yes |
| Interview Results | Working | session_detail + followup | Hybrid | SQL | Local summary | Yes |
| Company intelligence | Working | company_intel | Deterministic | companies/requirements | Disclaimer | Yes |
| Dream Company | Working | dream_company_analysis | Deterministic | SQL | Error payload | Yes |
| Opportunity Fit | Working | opportunity_fit | Deterministic | SQL | Empty list | Yes |
| Career Switch | Working | career_switch | Deterministic | N/A | Disclaimer | Yes |
| What-If | Working | what_if simulations | Deterministic | No mutate | Disclaimer | Yes |
| Analytics | Working | charts from SQL | Deterministic | progress/predictions | Empty charts | Partial |
| PDF Report | Working | ReportLab route | Deterministic | Generated on demand | N/A | Partial |
| Projects / GitHub | Working | github_project service | Deterministic analysis | projects.analysis_json | Manual add | Yes |
| Notifications | Working | Notification model | Deterministic | notifications | N/A | Partial |
| Admin | Working | admin blueprint | Deterministic | Catalog SQL | Auth gate | Yes |
| Company Comparison UI | Working | comparison + HTML cards | Deterministic | N/A | Error card | Yes |
| Career Comparison UI | Working | comparison + HTML cards | Deterministic | N/A | Error card | Yes |

## Provider matrix

| Provider | Config | Secret | Notes |
|----------|--------|--------|-------|
| local | `AI_PROVIDER=local` | none | Always available |
| groq | `AI_PROVIDER=groq` | `GROQ_API_KEY` | OpenAI-compatible API |
| openai | `AI_PROVIDER=openai` | `AI_API_KEY` | Chat Completions |
| gemini | `AI_PROVIDER=gemini` | `AI_API_KEY` | Gemini generateContent |

Fallback order for a request: configured primary → other configured cloud keys → local.
