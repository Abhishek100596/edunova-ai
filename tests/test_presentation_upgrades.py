"""Presentation upgrades: what-if UI, JD aliases, planner, mentor, health, normalize."""

from __future__ import annotations

from app.ai.response import normalize_ai_text
from app.extensions import db
from app.models import CareerRole, Project, StudentProfile, User
from app.services import jd_intel, learning_planner, personalization, project_mentor, what_if
from app.services.healthcheck import run_health_checks


def test_normalize_fenced_json_not_raw():
    raw = '```json\n{"answer": "Focus on SQL joins next.", "score": 90}\n```'
    text = normalize_ai_text(raw)
    assert "Focus on SQL" in text
    assert "```" not in text
    assert '{"answer"' not in text


def test_normalize_python_fence_removed():
    raw = "```python\n{'answer': 'Practice window functions', 'tips': ['joins']}\n```"
    text = normalize_ai_text(raw)
    assert "Practice window" in text or "window functions" in text
    assert "```" not in text


def test_jd_comparison_has_template_aliases(app):
    with app.app_context():
        student = User.query.filter_by(email="student@test.com").first()
        profile = StudentProfile.query.filter_by(user_id=student.id).first()
        text = (
            "Job Title: Data Analyst\nLocation: Remote\n"
            "Requirements: SQL, Python, Excel\nPreferred: Tableau"
        )
        result = jd_intel.compare_profile_to_jd(profile, text)
        assert "combined_fit_pct" in result
        assert "match_score" in result
        assert result["match_score"] == result["combined_fit_pct"]
        assert "matched_skills" in result
        assert "missing_skills" in result
        assert "label" in result
        assert "{" not in str(result["label"])


def test_what_if_html_no_dict_repr(client, app):
    client.post(
        "/login",
        data={"email": "student@test.com", "password": "Student@123", "submit": True},
        follow_redirects=True,
    )
    r = client.post(
        "/student/what-if",
        data={
            "scenario": "extra_projects",
            "extra_projects": "2",
            "submit": True,
        },
        follow_redirects=True,
    )
    assert r.status_code == 200
    body = r.data.decode("utf-8", errors="replace")
    assert "Simulation result" in body or "readiness" in body.lower()
    assert "overall_readiness" not in body  # raw key dump
    assert "'features':" not in body
    assert "placement_probability_estimate" not in body


def test_what_if_does_not_mutate_db(app):
    with app.app_context():
        student = User.query.filter_by(email="student@test.com").first()
        profile = StudentProfile.query.filter_by(user_id=student.id).first()
        before = Project.query.filter_by(student_id=profile.id).count()
        result = what_if.simulate_extra_projects(profile, 3)
        after = Project.query.filter_by(student_id=profile.id).count()
        assert before == after
        assert result["delta_overall_readiness"] is not None
        assert "disclaimer" in result


def test_learning_plan_deterministic(app):
    with app.app_context():
        student = User.query.filter_by(email="student@test.com").first()
        profile = StudentProfile.query.filter_by(user_id=student.id).first()
        role = CareerRole.query.filter_by(name="Data Analyst").first()
        plan = learning_planner.build_learning_plan(profile, role, weeks=4)
        assert plan["ok"] is True
        assert len(plan["weeks"]) == 4
        assert plan["weeks"][0]["focus_skill"]
        assert "hiring" not in plan["disclaimer"].lower() or "not" in plan["disclaimer"].lower()


def test_project_mentor_grounded(app):
    with app.app_context():
        student = User.query.filter_by(email="student@test.com").first()
        profile = StudentProfile.query.filter_by(user_id=student.id).first()
        project = Project(
            student_id=profile.id,
            title="Campus Analytics Dashboard",
            description="Flask dashboard for placement metrics",
            tech_stack="Python, Flask, SQL",
            analysis_status="manual",
        )
        db.session.add(project)
        db.session.commit()
        report = project_mentor.mentor_project(project, profile)
        assert report["ok"] is True
        assert report["title"] == "Campus Analytics Dashboard"
        assert "invent" not in report["disclaimer"].lower() or "not" in report["disclaimer"].lower()
        assert report["github_available"] is False


def test_career_snapshot_on_dashboard_intel(app):
    with app.app_context():
        student = User.query.filter_by(email="student@test.com").first()
        profile = StudentProfile.query.filter_by(user_id=student.id).first()
        intel = personalization.dashboard_intelligence(profile)
        snap = intel["career_snapshot"]
        assert snap["next_priority"]
        assert snap["strongest_areas"]
        assert "{" not in snap["next_priority"]


def test_admin_health_page(client, app):
    client.post(
        "/login",
        data={"email": "admin@test.com", "password": "Admin@123", "submit": True},
        follow_redirects=True,
    )
    r = client.get("/admin/health")
    assert r.status_code == 200
    body = r.data.decode("utf-8")
    assert "health" in body.lower() or "Checks" in body
    assert "GROQ_API_KEY" not in body
    assert "gsk_" not in body


def test_healthcheck_service(app):
    with app.app_context():
        report = run_health_checks()
        assert "checks" in report
        assert report["provider"]
        names = {c["name"] for c in report["checks"]}
        assert "database" in names
        assert "ai_provider" in names


def test_jd_analyzer_page_readable(client, app):
    client.post(
        "/login",
        data={"email": "student@test.com", "password": "Student@123", "submit": True},
        follow_redirects=True,
    )
    r = client.post(
        "/student/jd-analyzer",
        data={
            "title": "Analyst",
            "company": "Acme",
            "raw_text": "Job Title: Data Analyst\nRequirements: SQL Python Excel\nLocation: Bengaluru",
            "submit": True,
        },
        follow_redirects=True,
    )
    assert r.status_code == 200
    body = r.data.decode("utf-8", errors="replace")
    assert "Profile fit" in body or "fit" in body.lower()
    assert "<pre>" not in body or "skills_required" not in body
    assert "'combined_fit_pct'" not in body
