"""Mock interview question bank, evaluation, and session storage."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any

from flask import current_app

from app.ai.provider import LocalProvider, get_ai_provider
from app.extensions import db
from app.models.interview import InterviewAnswer, InterviewQuestion, InterviewSession
from app.models.profile import StudentProfile

QUESTION_BANK: dict[str, list[dict[str, Any]]] = {
    "behavioral": [
        {
            "prompt": "Tell me about a time you faced a difficult technical challenge and how you resolved it.",
            "keywords": [
                "challenge",
                "problem",
                "solution",
                "team",
                "learned",
                "result",
            ],
        },
        {
            "prompt": "Describe a project you are proud of and your specific contributions.",
            "keywords": [
                "project",
                "built",
                "responsibility",
                "impact",
                "technology",
                "outcome",
            ],
        },
        {
            "prompt": "How do you prioritize tasks when deadlines conflict?",
            "keywords": [
                "priority",
                "deadline",
                "communicate",
                "plan",
                "tradeoff",
                "stakeholder",
            ],
        },
    ],
    "technical": [
        {
            "prompt": "Explain how you would design a simple REST API for a student profile service.",
            "keywords": [
                "endpoint",
                "rest",
                "database",
                "authentication",
                "validation",
                "error",
            ],
        },
        {
            "prompt": "What is the difference between an array and a hash map, and when would you choose each?",
            "keywords": [
                "array",
                "hash",
                "lookup",
                "complexity",
                "memory",
                "order",
            ],
        },
        {
            "prompt": "Walk through debugging a production bug you have investigated.",
            "keywords": [
                "logs",
                "reproduce",
                "root cause",
                "fix",
                "test",
                "monitor",
            ],
        },
    ],
    "hr": [
        {
            "prompt": "Why do you want to join this company or role?",
            "keywords": [
                "role",
                "company",
                "growth",
                "skills",
                "mission",
                "contribute",
            ],
        },
        {
            "prompt": "Where do you see yourself in three years?",
            "keywords": [
                "learn",
                "career",
                "responsibility",
                "skills",
                "goals",
                "impact",
            ],
        },
        {
            "prompt": "What is a weakness you are actively improving?",
            "keywords": [
                "weakness",
                "improve",
                "practice",
                "feedback",
                "progress",
                "aware",
            ],
        },
    ],
}



ROLE_QUESTION_BANKS: dict[str, list[dict[str, Any]]] = {
    "data analyst": [
        {"prompt": "Walk through how you would write a SQL query with JOINs and window functions to rank students by GPA within each department.", "keywords": ["join", "window", "rank", "partition", "group", "aggregate"]},
        {"prompt": "How do you validate data quality before building a dashboard?", "keywords": ["null", "duplicate", "outlier", "schema", "validate", "clean"]},
        {"prompt": "Explain a dashboard you would build for placement readiness and which metrics matter.", "keywords": ["metric", "dashboard", "kpi", "trend", "filter", "stakeholder"]},
        {"prompt": "Describe the difference between INNER JOIN and LEFT JOIN with an example.", "keywords": ["inner", "left", "null", "match", "example", "table"]},
        {"prompt": "How would you communicate an unexpected insight to a non-technical stakeholder?", "keywords": ["stakeholder", "insight", "simple", "visual", "action", "impact"]},
    ],
    "data scientist": [
        {"prompt": "How do you prevent data leakage when training a classification model?", "keywords": ["leakage", "split", "pipeline", "validation", "feature", "train"]},
        {"prompt": "Compare precision and recall. When would you optimize for each?", "keywords": ["precision", "recall", "f1", "threshold", "false", "positive"]},
        {"prompt": "Describe feature engineering steps for a tabular prediction problem.", "keywords": ["feature", "encode", "scale", "missing", "interaction", "select"]},
        {"prompt": "How do you explain a model prediction to a business user?", "keywords": ["explain", "feature", "importance", "example", "limitation", "confidence"]},
        {"prompt": "What baselines would you try before a complex model?", "keywords": ["baseline", "mean", "logistic", "tree", "compare", "metric"]},
    ],
    "software engineer": [
        {"prompt": "Explain time and space complexity of searching in a hash map vs an array.", "keywords": ["hash", "array", "complexity", "average", "worst", "memory"]},
        {"prompt": "How would you design REST endpoints for creating and listing student skills?", "keywords": ["rest", "endpoint", "post", "get", "validation", "auth"]},
        {"prompt": "Describe how you use Git in a team workflow.", "keywords": ["branch", "pull", "request", "merge", "commit", "review"]},
        {"prompt": "What is the difference between process and thread?", "keywords": ["process", "thread", "memory", "concurrency", "isolation", "share"]},
        {"prompt": "How do you debug a failing API in production?", "keywords": ["log", "reproduce", "monitor", "root", "fix", "test"]},
    ],
    "machine learning engineer": [
        {"prompt": "How would you package and serve a trained model behind an API?", "keywords": ["api", "docker", "serialize", "version", "latency", "monitor"]},
        {"prompt": "What metrics and checks would you add for model drift?", "keywords": ["drift", "monitor", "distribution", "retrain", "threshold", "alert"]},
        {"prompt": "Explain train/serving skew and how to reduce it.", "keywords": ["skew", "pipeline", "feature", "serve", "consistent", "test"]},
        {"prompt": "When would you choose batch inference vs real-time inference?", "keywords": ["batch", "realtime", "latency", "cost", "throughput", "use"]},
        {"prompt": "How do you evaluate whether a model is ready for production?", "keywords": ["metric", "offline", "online", "latency", "error", "rollback"]},
    ],
    "business analyst": [
        {"prompt": "How do you gather and prioritize requirements from stakeholders?", "keywords": ["stakeholder", "requirement", "priority", "interview", "scope", "document"]},
        {"prompt": "Describe how you would use Excel or SQL to investigate a KPI drop.", "keywords": ["kpi", "filter", "trend", "segment", "hypothesis", "root"]},
        {"prompt": "What makes a good user story?", "keywords": ["user", "story", "criteria", "value", "acceptance", "clear"]},
        {"prompt": "How do you handle conflicting stakeholder requests?", "keywords": ["conflict", "priority", "tradeoff", "communicate", "impact", "align"]},
        {"prompt": "Explain how you would validate that a delivered feature meets the business need.", "keywords": ["accept", "test", "metric", "feedback", "demo", "success"]},
    ],
}


def _normalize_type(interview_type: str) -> str:
    key = (interview_type or "behavioral").strip().lower()
    if key not in QUESTION_BANK:
        return "behavioral"
    return key


def get_question_bank(interview_type: str | None = None) -> dict[str, list[dict[str, Any]]]:
    if interview_type:
        t = _normalize_type(interview_type)
        return {t: list(QUESTION_BANK[t])}
    return {k: list(v) for k, v in QUESTION_BANK.items()}


def keyword_coverage(answer_text: str, keywords: list[str]) -> float:
    if not keywords:
        return 0.0
    text = (answer_text or "").lower()
    hits = 0
    for kw in keywords:
        pattern = re.compile(r"\b" + re.escape(kw.lower()) + r"\b", re.I)
        if pattern.search(text):
            hits += 1
    return round(hits / len(keywords), 4)


def evaluate_answer_heuristics(
    answer_text: str, keywords: list[str]
) -> dict[str, Any]:
    """LocalProvider-style keyword coverage evaluation (AI-assisted label)."""
    coverage = keyword_coverage(answer_text, keywords)
    words = len(re.findall(r"\b\w+\b", answer_text or ""))
    length_factor = min(1.0, words / 80.0)
    score = round((0.7 * coverage + 0.3 * length_factor) * 100.0, 2)

    missing = [
        kw
        for kw in keywords
        if not re.search(r"\b" + re.escape(kw.lower()) + r"\b", (answer_text or "").lower())
    ]
    feedback_lines = [
        "[AI-assisted — LocalProvider heuristics] Evaluation uses keyword coverage "
        "and answer length; not a live LLM grade.",
        f"Keyword coverage: {coverage:.0%} ({len(keywords) - len(missing)}/{len(keywords)}).",
        f"Approximate score: {score}/100.",
    ]
    if words < 40:
        feedback_lines.append(
            "Answer is short — expand with situation, actions, and measurable results."
        )
    if missing:
        feedback_lines.append(
            "Consider addressing: " + ", ".join(missing[:8]) + "."
        )
    else:
        feedback_lines.append("Strong keyword coverage for this question.")

    # Optional LocalProvider narrative using the same heuristics context.
    local = LocalProvider()
    narrative = local.complete(
        "evaluate interview answer",
        system="Provide brief coaching based on keyword coverage only.",
        context={"skills": keywords, "coverage": coverage, "score": score},
    )
    feedback_lines.append(narrative)

    return {
        "score": score,
        "keyword_coverage": coverage,
        "feedback": "\n".join(feedback_lines),
        "missing_keywords": missing,
    }


def start_session(
    profile: StudentProfile,
    interview_type: str = "behavioral",
    *,
    role_focus: str | None = None,
    question_count: int = 5,
) -> InterviewSession:
    itype = _normalize_type(interview_type)
    bank = list(QUESTION_BANK[itype])
    # Blend role-specific questions when a known role focus is provided.
    role_key = (role_focus or "").strip().lower()
    for key, extra in ROLE_QUESTION_BANKS.items():
        if key in role_key or role_key in key:
            # Prefer role bank; keep a couple of generic questions of the selected type.
            bank = list(extra) + bank[:2]
            break
    # De-duplicate by prompt
    seen = set()
    unique = []
    for item in bank:
        p = item["prompt"]
        if p in seen:
            continue
        seen.add(p)
        unique.append(item)
    bank = unique
    count = max(1, min(int(question_count), len(bank)))

    session = InterviewSession(
        student_id=profile.id,
        interview_type=itype,
        role_focus=role_focus,
        status="in_progress",
    )
    db.session.add(session)
    db.session.flush()

    for idx, item in enumerate(bank[:count]):
        q = InterviewQuestion(
            session_id=session.id,
            order_index=idx,
            question_type=itype,
            prompt=item["prompt"],
            expected_keywords=json.dumps(item["keywords"]),
        )
        db.session.add(q)

    db.session.commit()
    return session


def submit_answer(
    question_id: int, answer_text: str
) -> InterviewAnswer:
    question = db.session.get(InterviewQuestion, question_id)
    if question is None:
        raise ValueError(f"InterviewQuestion id={question_id} not found.")

    try:
        keywords = json.loads(question.expected_keywords or "[]")
    except json.JSONDecodeError:
        keywords = [
            k.strip()
            for k in (question.expected_keywords or "").split(",")
            if k.strip()
        ]

    evaluation = evaluate_answer_heuristics(answer_text, list(keywords))

    answer = question.answer
    if answer is None:
        answer = InterviewAnswer(question_id=question.id)
        db.session.add(answer)

    answer.answer_text = answer_text or ""
    answer.score = evaluation["score"]
    answer.feedback = evaluation["feedback"]
    answer.keyword_coverage = evaluation["keyword_coverage"]
    answer.evaluated_at = datetime.now(timezone.utc)
    db.session.commit()
    return answer


def complete_session(session_id: int) -> InterviewSession:
    session = db.session.get(InterviewSession, session_id)
    if session is None:
        raise ValueError(f"InterviewSession id={session_id} not found.")

    scores: list[float] = []
    for q in session.questions or []:
        if q.answer is not None and q.answer.score is not None:
            scores.append(float(q.answer.score))

    session.overall_score = round(sum(scores) / len(scores), 2) if scores else 0.0
    session.status = "completed"
    session.completed_at = datetime.now(timezone.utc)
    weak = []
    strong = []
    for q in session.questions or []:
        if q.answer is None or q.answer.score is None:
            continue
        if float(q.answer.score) < 60:
            weak.append(q.prompt[:80])
        elif float(q.answer.score) >= 75:
            strong.append(q.prompt[:80])
    parts = [
        f"[AI-assisted heuristics] Completed {session.interview_type} interview",
        f"({session.role_focus or 'general'}) with {len(scores)} graded answers.",
        f"Overall: {session.overall_score}/100.",
    ]
    if strong:
        parts.append("Strong areas: " + "; ".join(strong[:2]) + ".")
    if weak:
        parts.append("Practice next: " + "; ".join(weak[:2]) + ".")
    session.summary = " ".join(parts)
    db.session.commit()
    return session


def session_detail(session_id: int) -> dict[str, Any]:
    session = db.session.get(InterviewSession, session_id)
    if session is None:
        raise ValueError(f"InterviewSession id={session_id} not found.")
    return {
        "id": session.id,
        "student_id": session.student_id,
        "interview_type": session.interview_type,
        "role_focus": session.role_focus,
        "status": session.status,
        "overall_score": session.overall_score,
        "summary": session.summary,
        "questions": [
            {
                "id": q.id,
                "order_index": q.order_index,
                "prompt": q.prompt,
                "answer": None
                if q.answer is None
                else {
                    "text": q.answer.answer_text,
                    "score": q.answer.score,
                    "feedback": q.answer.feedback,
                    "keyword_coverage": q.answer.keyword_coverage,
                },
            }
            for q in (session.questions or [])
        ],
    }


def coaching_followup(session: InterviewSession) -> str:
    """Optional richer feedback via configured AI provider (still no invention)."""
    prompt = (
        f"Summarize interview type={session.interview_type} role={session.role_focus} "
        f"overall_score={session.overall_score}. Give improvement tips."
    )
    try:
        provider = get_ai_provider(current_app.config)
        return provider.complete(
            prompt,
            system="You are an EDUNOVA AI interview coach. Do not invent candidate experience.",
            context={"score": session.overall_score, "type": session.interview_type},
        )
    except Exception as exc:  # noqa: BLE001
        local = LocalProvider()
        return local.complete(
            prompt + f" (provider error fallback: {exc})",
            system="EDUNOVA local interview coach fallback.",
            context={"score": session.overall_score, "type": session.interview_type},
        )
