"""Mock interview question bank, AI evaluation, and session storage."""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from typing import Any

from flask import current_app

from app.ai.provider import complete_with_fallback
from app.ai.response import format_interview_evaluation, normalize_ai_text
from app.extensions import db
from app.models.interview import InterviewAnswer, InterviewQuestion, InterviewSession
from app.models.profile import StudentProfile

logger = logging.getLogger(__name__)

QUESTION_BANK: dict[str, list[dict[str, Any]]] = {
    "behavioral": [
        {
            "prompt": "Tell me about a time you faced a difficult technical challenge and how you resolved it.",
            "keywords": ["challenge", "problem", "solution", "team", "learned", "result"],
        },
        {
            "prompt": "Describe a project you are proud of and your specific contributions.",
            "keywords": ["project", "built", "responsibility", "impact", "technology", "outcome"],
        },
        {
            "prompt": "How do you prioritize tasks when deadlines conflict?",
            "keywords": ["priority", "deadline", "communicate", "plan", "tradeoff", "stakeholder"],
        },
        {
            "prompt": "Tell me about a time you received critical feedback and how you responded.",
            "keywords": ["feedback", "improve", "listen", "change", "result", "learn"],
        },
        {
            "prompt": "Describe a situation where you collaborated with someone who had a different approach.",
            "keywords": ["collaborate", "conflict", "communicate", "compromise", "team", "outcome"],
        },
    ],
    "technical": [
        {
            "prompt": "Explain how you would design a simple REST API for a student profile service.",
            "keywords": ["endpoint", "rest", "database", "authentication", "validation", "error"],
        },
        {
            "prompt": "What is the difference between an array and a hash map, and when would you choose each?",
            "keywords": ["array", "hash", "lookup", "complexity", "memory", "order"],
        },
        {
            "prompt": "Walk through debugging a production bug you have investigated.",
            "keywords": ["logs", "reproduce", "root cause", "fix", "test", "monitor"],
        },
        {
            "prompt": "How would you secure user passwords in a web application?",
            "keywords": ["hash", "salt", "password", "store", "secure", "never"],
        },
        {
            "prompt": "Explain the difference between SQL JOIN types with a practical example.",
            "keywords": ["join", "inner", "left", "null", "table", "example"],
        },
    ],
    "hr": [
        {
            "prompt": "Why do you want to join this company or role?",
            "keywords": ["role", "company", "growth", "skills", "mission", "contribute"],
        },
        {
            "prompt": "Where do you see yourself in three years?",
            "keywords": ["learn", "career", "responsibility", "skills", "goals", "impact"],
        },
        {
            "prompt": "What is a weakness you are actively improving?",
            "keywords": ["weakness", "improve", "practice", "feedback", "progress", "aware"],
        },
        {
            "prompt": "How do you handle pressure before deadlines?",
            "keywords": ["plan", "priority", "communicate", "calm", "focus", "deliver"],
        },
        {
            "prompt": "Why should we hire you for an entry-level role?",
            "keywords": ["skills", "learn", "project", "team", "motivation", "value"],
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
    """Rule-based keyword coverage evaluation (honest fallback)."""
    coverage = keyword_coverage(answer_text, keywords)
    words = len(re.findall(r"\b\w+\b", answer_text or ""))
    length_factor = min(1.0, words / 80.0)
    score = round((0.7 * coverage + 0.3 * length_factor) * 100.0, 2)

    missing = [
        kw
        for kw in keywords
        if not re.search(r"\b" + re.escape(kw.lower()) + r"\b", (answer_text or "").lower())
    ]
    strengths = []
    weaknesses = []
    if coverage >= 0.5:
        strengths.append("Covered several expected themes for this question.")
    if words >= 60:
        strengths.append("Answer length suggests you explained the situation with some detail.")
    if words < 40:
        weaknesses.append("Answer is short — expand with situation, actions, and measurable results.")
    if missing:
        weaknesses.append("Some expected themes were not clearly mentioned.")

    better = (
        "Use a clear structure: context → what you did → why → result. "
        "Only reference experience you actually have."
    )
    if missing:
        better += " Consider addressing: " + ", ".join(missing[:6]) + "."

    structured = {
        "score": score,
        "keyword_coverage": coverage,
        "strengths": strengths or ["You attempted the question — keep practicing structure and depth."],
        "weaknesses": weaknesses,
        "missing_points": missing[:8],
        "better_answer_outline": better,
        "feedback": better,
        "evaluation_mode": "Rule-based evaluation",
        "mode": "Rule-based evaluation",
    }
    structured["feedback"] = format_interview_evaluation(structured)
    return structured


def _profile_facts_for_prompt(profile: StudentProfile | None) -> str:
    if profile is None:
        return "No profile attached."
    try:
        from app.services.coach import build_student_context

        ctx = build_student_context(profile)
        bits = [
            f"Name: {ctx.get('name')}",
            f"Degree/Branch: {ctx.get('degree')} {ctx.get('branch')}",
            f"Skills: {', '.join(ctx.get('skill_names') or [])[:300] or '(none)'}",
            f"Projects: {', '.join(ctx.get('project_titles') or [])[:300] or '(none)'}",
            f"Preferred roles: {ctx.get('preferred_roles')}",
        ]
        return " | ".join(bits)
    except Exception:
        return f"Student profile id={profile.id}"


def evaluate_answer_with_ai(
    *,
    question_prompt: str,
    answer_text: str,
    interview_type: str,
    role_focus: str | None,
    keywords: list[str],
    profile: StudentProfile | None = None,
) -> dict[str, Any]:
    """Primary AI evaluation when a cloud provider is configured; else heuristics."""
    primary = str(current_app.config.get("AI_PROVIDER", "local") or "local").lower()
    if primary in {"local", "demo", "local-demo"}:
        return evaluate_answer_heuristics(answer_text, keywords)

    system = (
        "You are an EDUNOVA AI interview evaluator for students. "
        "Score the answer 0-100. Be fair and constructive. "
        "Never invent candidate experience. "
        "Return ONLY a JSON object with keys: "
        "score (number), strengths (array of strings), weaknesses (array of strings), "
        "missing_points (array of strings), feedback (string), better_answer_outline (string). "
        "Do not wrap in markdown fences."
    )
    prompt = (
        f"Interview type: {interview_type}\n"
        f"Target role: {role_focus or 'general'}\n"
        f"Question: {question_prompt}\n"
        f"Expected themes (optional): {', '.join(keywords)}\n"
        f"Student profile facts: {_profile_facts_for_prompt(profile)}\n\n"
        f"Student answer:\n{answer_text}\n"
    )
    result = complete_with_fallback(
        current_app.config,
        prompt,
        system=system,
        context={"skills": keywords},
        history=None,
    )
    raw = result.get("reply") or ""
    # Try to parse JSON even if model added prose
    data: dict[str, Any] | None = None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", raw, re.S)
        if m:
            try:
                data = json.loads(m.group(0))
            except json.JSONDecodeError:
                data = None

    if not isinstance(data, dict) or "score" not in data:
        # Provider may have returned prose only — fall back to heuristics
        logger.info("AI interview eval parse failed; using rule-based fallback")
        fb = evaluate_answer_heuristics(answer_text, keywords)
        if result.get("fallback_used"):
            fb["evaluation_mode"] = "Rule-based evaluation"
        return fb

    try:
        score = float(data.get("score"))
    except (TypeError, ValueError):
        score = evaluate_answer_heuristics(answer_text, keywords)["score"]
    score = max(0.0, min(100.0, score))

    structured = {
        "score": round(score, 2),
        "keyword_coverage": keyword_coverage(answer_text, keywords),
        "strengths": data.get("strengths") or [],
        "weaknesses": data.get("weaknesses") or [],
        "missing_points": data.get("missing_points") or [],
        "better_answer_outline": data.get("better_answer_outline")
        or data.get("feedback")
        or "",
        "feedback": data.get("feedback") or "",
        "evaluation_mode": f"AI evaluation ({result.get('provider')})",
        "mode": f"AI evaluation ({result.get('provider')})",
    }
    structured["feedback"] = format_interview_evaluation(structured)
    return structured


def start_session(
    profile: StudentProfile,
    interview_type: str = "behavioral",
    *,
    role_focus: str | None = None,
    question_count: int = 5,
) -> InterviewSession:
    itype = _normalize_type(interview_type)
    bank = list(QUESTION_BANK[itype])
    role_key = (role_focus or "").strip().lower()
    for key, extra in ROLE_QUESTION_BANKS.items():
        if key in role_key or role_key in key:
            bank = list(extra) + bank[:2]
            break
    seen = set()
    unique = []
    for item in bank:
        p = item["prompt"]
        if p in seen:
            continue
        seen.add(p)
        unique.append(item)
    bank = unique
    count = max(1, min(int(question_count), len(bank), 5))

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
    question_id: int,
    answer_text: str,
    *,
    student_id: int | None = None,
) -> InterviewAnswer:
    question = db.session.get(InterviewQuestion, question_id)
    if question is None:
        raise ValueError("Interview question not found.")

    session = db.session.get(InterviewSession, question.session_id)
    if session is None:
        raise ValueError("Interview session not found.")
    if student_id is not None and session.student_id != student_id:
        raise PermissionError("You can only answer questions in your own interview session.")
    if session.status == "completed":
        raise ValueError("This interview session is already completed.")

    cleaned = (answer_text or "").strip()
    if not cleaned:
        raise ValueError("Please enter an answer before submitting.")
    if len(cleaned) > 5000:
        cleaned = cleaned[:5000]

    try:
        keywords = json.loads(question.expected_keywords or "[]")
    except json.JSONDecodeError:
        keywords = [
            k.strip()
            for k in (question.expected_keywords or "").split(",")
            if k.strip()
        ]

    profile = db.session.get(StudentProfile, session.student_id)
    evaluation = evaluate_answer_with_ai(
        question_prompt=question.prompt,
        answer_text=cleaned,
        interview_type=session.interview_type or "behavioral",
        role_focus=session.role_focus,
        keywords=list(keywords),
        profile=profile,
    )

    answer = question.answer
    if answer is None:
        answer = InterviewAnswer(question_id=question.id)
        db.session.add(answer)

    answer.answer_text = cleaned
    answer.score = evaluation["score"]
    answer.feedback = normalize_ai_text(evaluation["feedback"])
    answer.keyword_coverage = evaluation.get("keyword_coverage")
    answer.evaluated_at = datetime.now(timezone.utc)
    db.session.commit()
    return answer


def complete_session(
    session_id: int, *, student_id: int | None = None
) -> InterviewSession:
    session = db.session.get(InterviewSession, session_id)
    if session is None:
        raise ValueError("Interview session not found.")
    if student_id is not None and session.student_id != student_id:
        raise PermissionError("You can only complete your own interview session.")

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

    dims = _dimension_scores(session)
    parts = [
        f"Completed {session.interview_type} interview",
        f"({session.role_focus or 'general'}) with {len(scores)} graded answers.",
        f"Overall: {session.overall_score}/100.",
        f"Communication: {dims['communication']}/100 · Content: {dims['content']}/100 · "
        f"Structure: {dims['structure']}/100 · Role fit: {dims['role_fit']}/100.",
    ]
    if strong:
        parts.append("Strong areas: " + "; ".join(strong[:2]) + ".")
    if weak:
        parts.append("Practice next: " + "; ".join(weak[:2]) + ".")
    session.summary = " ".join(parts)

    # Optional AI narrative summary (non-authoritative)
    try:
        primary = str(current_app.config.get("AI_PROVIDER", "local") or "local").lower()
        if primary not in {"local", "demo", "local-demo"} and scores:
            ai = complete_with_fallback(
                current_app.config,
                (
                    f"Write a short interview debrief for a student. "
                    f"Type={session.interview_type}, role={session.role_focus}, "
                    f"overall={session.overall_score}, dims={dims}. "
                    f"Strong prompts: {strong[:2]}. Weak prompts: {weak[:2]}. "
                    "Do not invent experience. Use bullets."
                ),
                system="You are EDUNOVA interview coach. Natural language only. No JSON.",
            )
            narrative = normalize_ai_text(ai.get("reply") or "")
            if narrative:
                session.summary = session.summary + "\n\n" + narrative
    except Exception:  # noqa: BLE001
        pass

    db.session.commit()
    return session


def _dimension_scores(session: InterviewSession) -> dict[str, float]:
    scores = [
        float(q.answer.score)
        for q in (session.questions or [])
        if q.answer is not None and q.answer.score is not None
    ]
    if not scores:
        return {"communication": 0, "content": 0, "structure": 0, "role_fit": 0}
    overall = sum(scores) / len(scores)
    # Lightweight derived dims from answer length + scores (deterministic)
    lengths = []
    for q in session.questions or []:
        if q.answer and q.answer.answer_text:
            lengths.append(len(re.findall(r"\b\w+\b", q.answer.answer_text)))
    avg_len = sum(lengths) / len(lengths) if lengths else 0
    communication = round(min(100.0, overall * 0.7 + min(avg_len, 120) / 120 * 30), 1)
    content = round(overall, 1)
    structure = round(min(100.0, overall * 0.8 + (10 if avg_len >= 50 else 0)), 1)
    role_fit = round(overall, 1)
    return {
        "communication": communication,
        "content": content,
        "structure": structure,
        "role_fit": role_fit,
    }


def session_detail(session_id: int, *, student_id: int | None = None) -> dict[str, Any]:
    session = db.session.get(InterviewSession, session_id)
    if session is None:
        raise ValueError("Interview session not found.")
    if student_id is not None and session.student_id != student_id:
        raise PermissionError("You can only view your own interview session.")

    questions = sorted(session.questions or [], key=lambda q: q.order_index)
    answered = sum(1 for q in questions if q.answer is not None)
    current = None
    for q in questions:
        if q.answer is None:
            current = q
            break
    dims = _dimension_scores(session) if session.status == "completed" else None

    return {
        "id": session.id,
        "student_id": session.student_id,
        "interview_type": session.interview_type,
        "role_focus": session.role_focus,
        "status": session.status,
        "overall_score": session.overall_score,
        "summary": session.summary,
        "dimensions": dims,
        "question_count": len(questions),
        "answered_count": answered,
        "current_question_id": current.id if current else None,
        "current_question_number": (current.order_index + 1) if current else len(questions),
        "questions": [
            {
                "id": q.id,
                "order_index": q.order_index,
                "number": q.order_index + 1,
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
            for q in questions
        ],
    }


def coaching_followup(session: InterviewSession) -> str:
    """Richer debrief via configured AI provider (no invention)."""
    prompt = (
        f"Summarize interview type={session.interview_type} role={session.role_focus} "
        f"overall_score={session.overall_score}. Give improvement tips in bullets. "
        "Do not invent experience."
    )
    result = complete_with_fallback(
        current_app.config,
        prompt,
        system="You are an EDUNOVA AI interview coach. Natural language only.",
        context={"score": session.overall_score, "type": session.interview_type},
    )
    return normalize_ai_text(result.get("reply") or session.summary or "")
