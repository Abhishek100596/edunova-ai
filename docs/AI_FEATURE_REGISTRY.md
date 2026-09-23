# EduNova AI — Feature Registry

Educational career platform combining **deterministic intelligence**, **ML**, and **generative AI (Groq)**.

| Feature | AI? | Provider | Model | Fallback | Input | Output contract |
|---------|-----|----------|-------|----------|-------|-----------------|
| AI Career Coach | Yes | `AI_PROVIDER` (prod: groq) | `GROQ_MODEL` / `AI_MODEL` | Local smart coach | Profile context + message + history | Natural Markdown → HTML |
| Interview evaluation | Hybrid | Groq when configured | same | Heuristic scoring | Question + answer + keywords | Structured → formatted text |
| Interview follow-up | Yes | same | same | Local summary | Session results | Natural text |
| JD explanation | Hybrid | Deterministic extract/fit + optional AI narrative | same | Text-only fit panel | JD text + profile | Readable sections (not raw JSON) |
| What-If explanation | Hybrid | Deterministic sim + optional AI narrative | same | Numbers-only UI | Scenario params | Metrics + plain-language explanation |
| Learning planner | Hybrid | Deterministic weeks + optional AI overview | same | Weeks-only plan | Role + skill gaps | Weekly plan object → UI |
| Project mentor | Hybrid | Deterministic evidence + optional AI advice | same | Evidence-only cards | Project / GitHub analysis | Mentor report → UI |
| Career Snapshot | Deterministic | — | — | — | Dashboard intel | Snapshot dict → dashboard cards |
| Roadmap | Deterministic | — | — | — | Skill gaps | DB tasks + progress |
| Placement prediction | ML | joblib model | — | Logistic fallback | Feature vector | Probability + factors |
| Skill gap / careers / company fit | Deterministic | — | — | — | Catalog + profile | Scores + lists |
| Resume / JD extract | Deterministic | — | — | — | Upload / text | Heuristic analysis |

## Environment

```
AI_PROVIDER=groq
AI_API_KEY=          # or GROQ_API_KEY
AI_MODEL=openai/gpt-oss-120b
GROQ_API_KEY=
GROQ_MODEL=openai/gpt-oss-120b
```

Never commit real keys. Admin → **Health Check** verifies configuration without exposing secrets.
