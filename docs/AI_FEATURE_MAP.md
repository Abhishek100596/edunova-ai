# EDUNOVA AI — Feature Map

| Feature | Input | Processing | Technology | Output | Limitations |
|---------|-------|------------|------------|--------|-------------|
| Placement prediction | Profile academics + skills/experience counts | Supervised classification | scikit-learn joblib | Probability + readiness | Synthetic training data; estimate only |
| Explainability | Feature vector + model | Importances / contributions | Deterministic math | +/− factors | Not full SHAP in default path |
| Intelligence score | Profile + related tables | Weighted dimensions | Rules | Overall + how_calculated | Decision support only |
| Skill confidence | Skills + projects/certs/internships/interviews | Evidence weighting | Rules | Confidence label | Heuristic, not biometric |
| Career match | Skills vs role requirements | Weighted scoring | Rules | Ranked roles + gaps | Catalog-bound |
| Skill gap matrix | Target role | Level + importance + confidence | Rules | Priority matrix | “Not yet evidenced” ≠ proven absence |
| Opportunity fit | Profile + company requirements | Fit % buckets | Rules | Company–role table | Compatibility estimate |
| Dream company | Company + role | Requirement merge + readiness | Rules | Gap + evidence list | Not a hiring guarantee |
| What-if | Hypothetical skill/projects | Feature clone recompute | Rules | Delta readiness | Scenario simulation only |
| Career switch | Current/target roles | Transferable vs missing | Rules | Staged plan | Catalog-based |
| Company/career compare | Two IDs | Side-by-side scoring | Rules | Diff table | No unsupported rankings |
| Roadmap | Gaps | Template phases | Rules | Tasks + progress % | Manual completion |
| Resume parse | PDF/DOCX | Text extract + keywords | NLP heuristics | Skills/sections | Parser imperfect |
| Resume–JD / JD analyzer | Texts | TF-IDF + structured extract | sklearn + rules | Match / missing | Not vendor ATS |
| Interview eval | Answer text | Keywords / optional LLM | Heuristic or GenAI | AI-assisted scores | Subjective |
| Coach | Question + profile | Context + provider | Local/Gemini/OpenAI | Guidance | Local = demo quality |
| Report 2.0 | Aggregated stored data | ReportLab PDF | Deterministic | PDF file | Snapshot; no filler history |
| Evidence layer | Admin/seed catalog | Provenance metadata | SQLAlchemy | Sources + status | Curated, not live scrape |
