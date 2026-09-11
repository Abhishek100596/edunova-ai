# NEXORA AI — Viva Guide (75+ Q&A)

## Python / Flask
**Q1. What is Flask?**  
Short: Lightweight Python web framework.  
Detailed: Uses Werkzeug WSGI and Jinja2 templates; NEXORA uses an application factory `create_app()`.  
NEXORA: Routes under `app/routes/`.

**Q2. What is an application factory?**  
Creates the app in a function for testing and multiple configs. NEXORA: `create_app(TestConfig)` in pytest.

**Q3. CSRF?**  
Cross-Site Request Forgery protection via Flask-WTF tokens on forms.

**Q4. Flask-Login?**  
Session-based auth; `current_user`, `@login_required`.

**Q5. Blueprints?**  
Modular route groups: auth, student, admin, api, main.

## SQL / Database
**Q6. What is SQLAlchemy?** ORM mapping classes to tables.  
**Q7. Why foreign keys?** Referential integrity (profile→user).  
**Q8. What is a migration?** Schema versioning (Flask-Migrate available).  
**Q9. SQLite vs Postgres?** SQLite for local demo; Postgres for production scale.  
**Q10. N+1 query problem?** Load related objects carefully; use joins when needed.

## Machine Learning
**Q11. Classification vs regression?** Placement placed/not + probability is classification with predict_proba.  
**Q12. Train/test split?** Hold out data to estimate generalization.  
**Q13. Cross-validation?** Multiple folds for robust metrics.  
**Q14. Overfitting?** Model memorizes train set; high train / low test performance.  
**Q15. Underfitting?** Too simple to capture signal.  
**Q16. Accuracy limitation?** Misleading on imbalanced classes.  
**Q17. Precision?** Of predicted positives, how many correct.  
**Q18. Recall?** Of actual positives, how many found.  
**Q19. F1?** Harmonic mean of precision & recall.  
**Q20. ROC-AUC?** Ranking quality across thresholds — used to pick NEXORA’s best model.  
**Q21. Logistic Regression?** Linear log-odds classifier; interpretable coefficients.  
**Q22. Random Forest?** Ensemble of trees; feature_importances_.  
**Q23. Gradient Boosting?** Sequential trees correcting residuals.  
**Q24. Feature engineering?** Building cgpa, skill_count, etc. from profile.  
**Q25. Data leakage?** Using future/label info in features — avoided in NEXORA pipeline.  
**Q26. Why not retrain on every request?** Costly; NEXORA loads joblib at prediction time.  
**Q27. Synthetic data ethics?** Must be labelled as synthetic — NEXORA documents this.  
**Q28. Calibration?** Probabilities may need calibration; we report estimates, not certainty.

## Explainable AI
**Q29. What is explainability?** Reasons humans can understand for a prediction.  
**Q30. Feature importance?** How much each feature influences the model.  
**Q31. SHAP?** Game-theoretic feature attributions (optional advanced path).  
**Q32. NEXORA approach?** Contributions + positive/negative factor lists.  
**Q33. Why explain placement?** Builds trust; academic evaluation requires transparency.

## NLP / GenAI
**Q34. NLP?** Processing human language text.  
**Q35. TF-IDF?** Term frequency–inverse document frequency vectors.  
**Q36. Cosine similarity?** Angle between vectors — Resume–JD score.  
**Q37. Embedding?** Dense vector semantic representation.  
**Q38. LLM?** Large language model for generation/reasoning.  
**Q39. Prompt engineering?** Structuring instructions/context for LLMs.  
**Q40. RAG?** Retrieve grounding docs then generate — coach uses profile context similarly.  
**Q41. Hallucination risk?** LLMs invent facts — NEXORA forbids inventing skills/jobs.  
**Q42. LocalProvider?** Deterministic/demo GenAI without API keys.  
**Q43. Why modular AIProvider?** Swap Gemini/OpenAI without rewriting routes.

## Recommendation systems
**Q44. Content-based filtering?** Match user attributes to item attributes — role skills.  
**Q45. Collaborative filtering?** User–user patterns — not primary in NEXORA.  
**Q46. Hybrid?** Rules + optional LLM explanations.  
**Q47. Why not let LLM invent match %?** Scores must be reproducible and auditable.

## Security
**Q48. Password hashing?** One-way hash (Werkzeug); never store plaintext.  
**Q49. XSS?** Escape outputs; Jinja autoescape.  
**Q50. SQL injection?** ORM parameterization.  
**Q51. Session security?** HTTPOnly cookies, SameSite.  
**Q52. File upload risks?** Validate type/size; never execute uploads.  
**Q53. Authorization vs authentication?** AuthN = who you are; AuthZ = what you may do.  
**Q54. Why students can’t open /admin?** `role_required("admin")`.  
**Q55. Secrets management?** `.env` / environment; never commit keys.  
**Q56. Rate limiting?** Soft limits on sensitive endpoints where practical.  
**Q57. Prompt injection?** Malicious resume text trying to override coach — sanitize/limit context.

## Frontend / Product
**Q58. Why Chart.js?** Lightweight browser charts for real history.  
**Q59. Dark/light tokens?** CSS variables for consistent theming.  
**Q60. Glassmorphism risk?** Contrast/accessibility — used sparingly.  
**Q61. Empty states?** Honest UX when no data.  
**Q62. Demo mode label?** Avoid pretending local heuristics are cloud LLM.

## Architecture
**Q63. MVC-ish layers?** Routes → services → models.  
**Q64. Why services?** Keep routes thin; reusable business logic.  
**Q65. Blueprint urls?** `/student/*`, `/admin/*`, `/api/*`.  
**Q66. PredictionRecord?** Stores history for analytics (no fabricated charts).  
**Q67. Placement readiness vs probability?** Readiness = multi-factor score; probability = ML estimate.  
**Q68. ATS claim?** We say Resume–JD Compatibility, not vendor ATS.  
**Q69. Employment guarantee?** Explicitly disclaimed.  
**Q70. How to retrain?** `python -m ml.training.train_placement`.  
**Q71. How to seed demo?** `python scripts/seed.py` (idempotent).  
**Q72. pytest purpose?** Regression tests for auth/ML/gaps.  
**Q73. Gunicorn?** Production WSGI server option.  
**Q74. Biggest risk academically?** Overclaiming AI — mitigated by feature map honesty.  
**Q75. One-line pitch?** NEXORA AI turns a student profile into explainable placement readiness, skill gaps, and practice loops.

## Extra
**Q76. Confusion matrix?** TP/FP/TN/FN counts for classifiers.  
**Q77. Class imbalance?** Affects accuracy; ROC-AUC helps.  
**Q78. Softmax vs sigmoid?** Binary logistic uses sigmoid.  
**Q79. Hyperparameters?** Tree depth, n_estimators, C for LR.  
**Q80. Model versioning?** Meta JSON stores algorithm + metrics + date.
