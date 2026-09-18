"""Tests for Groq provider, response normalization, interview ownership, API coach."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from app.ai.provider import GroqProvider, LocalProvider, complete_with_fallback, get_ai_provider
from app.ai.response import format_interview_evaluation, normalize_ai_text
from app.extensions import db
from app.models import CareerRole, StudentProfile, User
from app.models.interview import InterviewSession
from app.services import coach as coach_svc
from app.services import interview as interview_svc
from app.services import roadmap as roadmap_svc


def test_normalize_strips_json_wrapper():
    raw = '```json\n{"answer": "Learn SQL next.", "score": 80}\n```'
    text = normalize_ai_text(raw)
    assert "{" not in text or "Learn SQL" in text
    assert "Learn SQL" in text
    assert "```" not in text


def test_normalize_python_dict_string():
    text = normalize_ai_text("{'answer': 'Practice joins', 'feedback': 'Good'}")
    assert "Practice joins" in text
    assert "Good" in text


def test_format_interview_evaluation_readable():
    text = format_interview_evaluation(
        {
            "score": 78,
            "strengths": ["Clear structure"],
            "weaknesses": ["More metrics"],
            "missing_points": ["tradeoffs"],
            "better_answer_outline": "Add a measurable result.",
            "evaluation_mode": "AI evaluation (groq)",
        }
    )
    assert "Score: 78/100" in text
    assert "Clear structure" in text
    assert "{" not in text


def test_local_provider_no_demo_spam():
    reply = LocalProvider().complete("What should I learn next?", context={"skill_names": ["Python", "SQL"]})
    assert "[LocalProvider]" not in reply
    assert "Context used:" not in reply
    assert "Your question:" not in reply


def test_get_ai_provider_groq(app):
    with app.app_context():
        p = get_ai_provider(
            {
                "AI_PROVIDER": "groq",
                "GROQ_API_KEY": "test-key",
                "GROQ_MODEL": "openai/gpt-oss-120b",
            }
        )
        assert p.name == "groq"
        assert isinstance(p, GroqProvider)
        assert p.model == "openai/gpt-oss-120b"


def test_groq_accepts_ai_api_key_alias(app):
    """Production Render style: AI_PROVIDER=groq + AI_API_KEY + AI_MODEL."""
    with app.app_context():
        from app.ai.provider import resolve_groq_credentials

        key, model = resolve_groq_credentials(
            {
                "AI_PROVIDER": "groq",
                "AI_API_KEY": "gsk_test_key",
                "AI_MODEL": "openai/gpt-oss-120b",
                "GROQ_API_KEY": "",
                "GROQ_MODEL": "",
            }
        )
        assert key == "gsk_test_key"
        assert model == "openai/gpt-oss-120b"
        p = get_ai_provider(
            {
                "AI_PROVIDER": "groq",
                "AI_API_KEY": "gsk_test_key",
                "AI_MODEL": "openai/gpt-oss-120b",
            }
        )
        assert p.name == "groq"
        assert p.api_key == "gsk_test_key"


def test_demo_mode_does_not_force_local_provider():
    from app.ai.provider import get_ai_provider

    p = get_ai_provider(
        {
            "AI_PROVIDER": "groq",
            "DEMO_MODE": True,
            "AI_API_KEY": "gsk_x",
            "AI_MODEL": "openai/gpt-oss-120b",
        }
    )
    assert p.name == "groq"


def test_groq_missing_key_raises():
    p = GroqProvider(api_key="")
    with pytest.raises(RuntimeError) as excinfo:
        p.complete("hello")
    msg = str(excinfo.value)
    assert "AI_API_KEY" in msg or "GROQ_API_KEY" in msg
    assert "gsk_" not in msg


def test_factory_local_gemini_openai_aliases():
    assert get_ai_provider({"AI_PROVIDER": "local"}).name == "local"
    assert get_ai_provider({"AI_PROVIDER": "demo"}).name == "local"
    assert get_ai_provider({"AI_PROVIDER": "local-demo"}).name == "local"
    gem = get_ai_provider({"AI_PROVIDER": "gemini", "AI_API_KEY": "k", "AI_MODEL": "m"})
    assert gem.name == "gemini"
    goog = get_ai_provider({"AI_PROVIDER": "google", "AI_API_KEY": "k"})
    assert goog.name == "gemini"
    oai = get_ai_provider({"AI_PROVIDER": "openai", "AI_API_KEY": "k", "AI_MODEL": "gpt-4o-mini"})
    assert oai.name == "openai"
    gpt = get_ai_provider({"AI_PROVIDER": "gpt", "AI_API_KEY": "k"})
    assert gpt.name == "openai"
    with pytest.raises(ValueError) as excinfo:
        get_ai_provider({"AI_PROVIDER": "unknown-cloud"})
    assert "groq" in str(excinfo.value).lower()


def test_groq_malformed_response_raises(app):
    class _Resp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return json.dumps({"choices": []}).encode("utf-8")

    with app.app_context():
        real_import = __import__

        def fake_import(name, *args, **kwargs):
            if name == "groq":
                raise ImportError("no groq")
            return real_import(name, *args, **kwargs)

        with patch("urllib.request.urlopen", return_value=_Resp()):
            with patch("builtins.__import__", side_effect=fake_import):
                p = GroqProvider(api_key="fake-key", model="openai/gpt-oss-120b")
                with pytest.raises(RuntimeError) as excinfo:
                    p.complete("What next?")
        assert "Unexpected" in str(excinfo.value)
        assert "fake-key" not in str(excinfo.value)


def test_groq_provider_mocked_success(app):
    payload = {
        "choices": [{"message": {"content": "Focus on SQL window functions next."}}]
    }

    class _Resp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return json.dumps(payload).encode("utf-8")

    with app.app_context():
        with patch("urllib.request.urlopen", return_value=_Resp()):
            with patch.dict("sys.modules", {"groq": None}):
                # Force HTTP path by making groq import fail inside complete
                import app.ai.provider as prov

                real_import = __import__

                def fake_import(name, *args, **kwargs):
                    if name == "groq":
                        raise ImportError("no groq")
                    return real_import(name, *args, **kwargs)

                with patch("builtins.__import__", side_effect=fake_import):
                    p = GroqProvider(api_key="fake-key", model="openai/gpt-oss-120b")
                    out = p.complete(
                        "What next?", system="Coach", context={"skill_names": ["SQL"]}
                    )
            assert "SQL" in out


def test_complete_with_fallback_to_local(app):
    with app.app_context():
        cfg = {
            "AI_PROVIDER": "groq",
            "GROQ_API_KEY": "bad-key",
            "GROQ_MODEL": "openai/gpt-oss-120b",
            "AI_API_KEY": "",
        }

        def _boom(*a, **k):
            raise RuntimeError("fail")

        with patch.object(GroqProvider, "complete", side_effect=_boom):
            result = complete_with_fallback(
                cfg, "What should I learn next?", context={"skill_names": ["Python"]}
            )
            assert result["provider"] == "local"
            assert result["fallback_used"] is True
            assert result["reply"]
            assert "GROQ_API_KEY" not in result["reply"]
            assert "bad-key" not in result["reply"]


def test_coach_no_raw_json(app):
    with app.app_context():
        student = User.query.filter_by(email="student@test.com").first()
        profile = StudentProfile.query.filter_by(user_id=student.id).first()
        coach_svc.clear_conversation(profile)
        r = coach_svc.ask_coach(profile, "What should I learn next?")
        assert r["reply"]
        assert '"answer"' not in r["reply"]
        assert "```json" not in r["reply"]
        assert "[Local coach]" not in r["reply"]


def test_interview_session_and_ownership(app):
    with app.app_context():
        student = User.query.filter_by(email="student@test.com").first()
        profile = StudentProfile.query.filter_by(user_id=student.id).first()
        other = User(email="other@test.com", name="Other", role="student")
        other.set_password("Other@123")
        db.session.add(other)
        db.session.commit()
        from app.models import StudentProfile as SP

        other_profile = SP(user_id=other.id, onboarding_pct=100)
        db.session.add(other_profile)
        db.session.commit()

        sess = interview_svc.start_session(profile, "technical", role_focus="Data Analyst", question_count=5)
        detail = interview_svc.session_detail(sess.id, student_id=profile.id)
        assert detail["question_count"] == 5
        qid = detail["questions"][0]["id"]

        ans = interview_svc.submit_answer(
            qid,
            "I would use SQL joins and window functions to rank GPA by department, validate nulls, then share a dashboard KPI.",
            student_id=profile.id,
        )
        assert ans.score is not None
        assert "Score:" in (ans.feedback or "") or "/100" in (ans.feedback or "")
        assert "```" not in (ans.feedback or "")

        with pytest.raises(PermissionError):
            interview_svc.submit_answer(qid, "hack", student_id=other_profile.id)

        interview_svc.complete_session(sess.id, student_id=profile.id)
        done = db.session.get(InterviewSession, sess.id)
        assert done.status == "completed"
        assert done.overall_score is not None

        with pytest.raises(PermissionError):
            interview_svc.session_detail(sess.id, student_id=other_profile.id)


def test_interview_ai_eval_mocked(app):
    with app.app_context():
        student = User.query.filter_by(email="student@test.com").first()
        profile = StudentProfile.query.filter_by(user_id=student.id).first()
        app.config["AI_PROVIDER"] = "groq"
        app.config["GROQ_API_KEY"] = "fake"

        fake = {
            "reply": json.dumps(
                {
                    "score": 82,
                    "strengths": ["Clear SQL thinking"],
                    "weaknesses": ["Add an example"],
                    "missing_points": ["indexes"],
                    "feedback": "Solid start",
                    "better_answer_outline": "Mention an example query.",
                }
            ),
            "provider": "groq",
            "fallback_used": False,
            "status_message": "",
        }
        with patch("app.services.interview.complete_with_fallback", return_value=fake):
            result = interview_svc.evaluate_answer_with_ai(
                question_prompt="Explain JOINs",
                answer_text="INNER JOIN returns matches; LEFT JOIN keeps left rows.",
                interview_type="technical",
                role_focus="Data Analyst",
                keywords=["join", "inner", "left"],
                profile=profile,
            )
        assert result["score"] == 82
        assert "Rule-based" not in result["evaluation_mode"]
        assert "Clear SQL" in result["feedback"]


def test_roadmap_adaptive_tasks(app):
    with app.app_context():
        student = User.query.filter_by(email="student@test.com").first()
        profile = StudentProfile.query.filter_by(user_id=student.id).first()
        role = CareerRole.query.filter_by(name="Data Analyst").first()
        rm = roadmap_svc.generate_roadmap(profile, role, replace_existing=True)
        summary = roadmap_svc.roadmap_summary(rm)
        titles = " ".join(t["title"] for t in summary["tasks"]).lower()
        assert "strengthen" in titles or "build" in titles or "portfolio" in titles
        assert "job applications" in titles or "applications" in titles
        assert summary["progress_pct"] == 0 or summary["progress_pct"] >= 0
        task_id = summary["tasks"][0]["id"]
        roadmap_svc.set_task_status(task_id, "completed", student_id=profile.id)
        again = roadmap_svc.roadmap_summary(rm)
        assert again["progress_pct"] > 0


def test_api_coach_endpoints(client, app):
    client.post(
        "/login",
        data={"email": "student@test.com", "password": "Student@123", "submit": True},
        follow_redirects=True,
    )
    r = client.post("/api/coach", json={})
    assert r.status_code == 400
    r = client.post("/api/coach", json={"message": "x" * 2001})
    assert r.status_code == 400
    r = client.post("/api/coach", json={"message": "What should I learn next?"})
    assert r.status_code == 200
    data = r.get_json()
    assert "reply" in data
    assert "detail" not in data
    assert "GROQ_API_KEY" not in json.dumps(data)
