# NEXORA AI — Academic Project Document

## Abstract
NEXORA AI is an AI-powered career intelligence platform that helps students assess placement readiness, discover fitting roles, close skill gaps, improve resumes, practice interviews, and track progress using machine learning, NLP, and optional generative AI.

## Problem statement
Students lack an integrated, explainable system connecting academic profiles to career decisions.

## Proposed system
A Flask web application with ML placement estimates, rule-based career/skill analysis, NLP resume tools, and pluggable GenAI coaching — with demo mode when no API key is configured.

## Objectives
- Predict placement readiness with explainable factors
- Recommend careers and learning paths from real profile data
- Analyze resumes against job descriptions transparently
- Support interview practice with labelled AI-assisted feedback
- Provide secure student/admin separation

## Methodology
Synthetic educational dataset → train/compare classifiers → persist best model → serve predictions; hybrid recommendation (rules + optional LLM explanations); TF-IDF for text similarity.

## Dataset
Synthetic CSV (`ml/datasets/placement_synthetic.csv`) — **not real placement outcomes**. Features documented in training script. Limitations: distributional bias, academic-only use.

## Results (example after training)
Best model selected by ROC-AUC among Logistic Regression, Random Forest, Gradient Boosting. Exact metrics stored in `ml/models/placement_meta.json`.

## Limitations
Synthetic data; GenAI quality depends on provider; no employment guarantee.

## Future scope
Real institutional datasets, SHAP dashboards, richer embeddings, mobile app.

## Conclusion
NEXORA AI demonstrates a coherent career-intelligence loop from profile → ML → explainability → recommendations → practice → progress.
