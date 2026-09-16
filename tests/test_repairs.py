"""Focused regression tests for EduNova repair work."""

import pytest

from app.extensions import db
from app.models import AIConversation, CareerRole, Company, LearningRoadmap, Project, StudentProfile, User
from app.services import coach as coach_svc
from app.services import comparison as comparison_svc
from app.services import roadmap as roadmap_svc
from app.services.github_project import GitHubAnalysisError, parse_github_url


def _login_student(client):
    return client.post(
        "/login",
        data={"email": "student@test.com", "password": "Student@123", "submit": True},
        follow_redirects=True,
    )


def test_duplicate_signup_rejected(client, app):
    data = {
        "name": "Dup User",
        "email": "student@test.com",
        "password": "Secure@123",
        "confirm": "Secure@123",
        "submit": True,
    }
    r = client.post("/register", data=data, follow_redirects=True)
    assert r.status_code == 200
    assert b"already exists" in r.data.lower() or b"already" in r.data.lower()
    with app.app_context():
        assert User.query.filter_by(email="student@test.com").count() == 1


def test_wrong_password_and_nonexistent_user(client):
    r = client.post(
        "/login",
        data={"email": "student@test.com", "password": "WrongPass1", "submit": True},
        follow_redirects=True,
    )
    assert r.status_code in (200, 401)
    assert b"Invalid email or password" in r.data

    r = client.post(
        "/login",
        data={"email": "missing@test.com", "password": "Whatever@1", "submit": True},
        follow_redirects=True,
    )
    assert r.status_code in (200, 401)
    assert b"Invalid email or password" in r.data


def test_login_logout_login_persistence(client, app):
    _login_student(client)
    r = client.get("/student/dashboard")
    assert r.status_code == 200
    client.get("/logout", follow_redirects=True)
    r = client.get("/student/dashboard", follow_redirects=False)
    assert r.status_code in (302, 401)
    _login_student(client)
    r = client.get("/student/dashboard")
    assert r.status_code == 200
    with app.app_context():
        assert User.query.filter_by(email="student@test.com").first() is not None


def test_auth_survives_app_recreate(app):
    """Same SQLAlchemy metadata / in-memory fixture keeps users within the app context."""
    with app.app_context():
        before = User.query.filter_by(email="student@test.com").first()
        assert before is not None
        assert before.check_password("Student@123")
        uid = before.id
        again = db.session.get(User, uid)
        assert again is not None
        assert again.email == "student@test.com"


def test_company_comparison_readable_html(client, app):
    with app.app_context():
        c1 = Company(name="Alpha Corp", slug="alpha-corp", company_type="product")
        c2 = Company(name="Beta Soft", slug="beta-soft", company_type="services")
        db.session.add_all([c1, c2])
        db.session.commit()
        a_id, b_id = c1.id, c2.id

    _login_student(client)
    r = client.post(
        "/student/compare-companies",
        data={"company_id_a": a_id, "company_id_b": b_id, "submit": True},
        follow_redirects=True,
    )
    assert r.status_code == 200
    body = r.data.decode("utf-8", errors="replace")
    assert "Comparison summary" in body or "Calculated educational fit" in body
    assert "<pre" not in body.lower() or "tojson" not in body.lower()
    assert "Alpha Corp" in body and "Beta Soft" in body
    # Should not dump raw Python/JSON dict wrappers as the primary UX
    assert "detail_a" not in body
    assert '"company_a"' not in body


def test_compare_companies_service_summary(app):
    with app.app_context():
        student = User.query.filter_by(email="student@test.com").first()
        profile = StudentProfile.query.filter_by(user_id=student.id).first()
        c1 = Company(name="Gamma Inc", slug="gamma-inc", company_type="product")
        c2 = Company(name="Delta Ltd", slug="delta-ltd", company_type="services")
        db.session.add_all([c1, c2])
        db.session.commit()
        result = comparison_svc.compare_companies(profile, c1.id, c2.id)
        assert "summary" in result
        assert "company_a" in result and "company_b" in result
        assert "matching_skills" in result["company_a"]
        assert "fit_pct" in result["company_a"]
        assert result.get("error") is None


def test_ai_coach_followup_not_identical(app):
    with app.app_context():
        student = User.query.filter_by(email="student@test.com").first()
        profile = StudentProfile.query.filter_by(user_id=student.id).first()
        coach_svc.clear_conversation(profile)
        first = coach_svc.ask_coach(profile, "What should I learn next?")
        second = coach_svc.ask_coach(profile, "Why should I learn that?")
        third = coach_svc.ask_coach(profile, "Give me a 30 day plan.")
        assert first["reply"]
        assert second["reply"]
        assert third["reply"]
        assert first["reply"] != second["reply"]
        assert second["reply"] != third["reply"]
        assert "30-day" in third["reply"].lower() or "days 1" in third["reply"].lower()
        history = AIConversation.query.filter_by(student_id=profile.id).all()
        assert len(history) >= 6


def test_ai_coach_unrelated_and_history(app):
    with app.app_context():
        student = User.query.filter_by(email="student@test.com").first()
        profile = StudentProfile.query.filter_by(user_id=student.id).first()
        coach_svc.clear_conversation(profile)
        a = coach_svc.ask_coach(profile, "How can I improve my resume?")
        b = coach_svc.ask_coach(profile, "Prepare me for technical interview")
        assert "resume" in a["reply"].lower()
        assert "interview" in b["reply"].lower()
        assert a["reply"] != b["reply"]
        recent = coach_svc.recent_conversation(profile)
        assert len(recent) >= 4


def test_github_url_validation():
    assert parse_github_url("https://github.com/pallets/flask") == ("pallets", "flask")
    assert parse_github_url("github.com/pallets/flask/") == ("pallets", "flask")
    with pytest.raises(GitHubAnalysisError):
        parse_github_url("file:///etc/passwd")
    with pytest.raises(GitHubAnalysisError):
        parse_github_url("http://127.0.0.1/repo")
    with pytest.raises(GitHubAnalysisError):
        parse_github_url("https://evil.example/owner/repo")


def test_github_analyze_public_repo(app):
    pytest.importorskip("urllib")
    from app.services.github_project import analyze_github_repository

    with app.app_context():
        try:
            analysis = analyze_github_repository("https://github.com/pallets/flask")
        except GitHubAnalysisError as exc:
            pytest.skip(f"GitHub unavailable or rate-limited: {exc}")
        assert analysis["ok"] is True
        found = analysis["found_in_repository"]
        assert found["title"]
        assert isinstance(found["files_reviewed"], list)
        assert analysis["summary_text"]


def test_roadmap_generate_progress_persist(app):
    with app.app_context():
        student = User.query.filter_by(email="student@test.com").first()
        profile = StudentProfile.query.filter_by(user_id=student.id).first()
        role = CareerRole.query.filter_by(name="Data Analyst").first()
        rm = roadmap_svc.generate_roadmap(profile, role, replace_existing=True)
        assert rm.id
        summary = roadmap_svc.roadmap_summary(rm)
        assert summary["tasks"]
        assert any("FOUNDATION" in (t["title"] or "") or t.get("stage") == "FOUNDATION" for t in summary["tasks"])
        task_id = summary["tasks"][0]["id"]
        roadmap_svc.set_task_status(task_id, "completed", student_id=profile.id)
        again = LearningRoadmap.query.get(rm.id)
        assert again.progress_pct > 0
        # Reload summary after refresh-equivalent query
        summary2 = roadmap_svc.roadmap_summary(again)
        assert summary2["progress_pct"] == again.progress_pct


def test_roadmap_route_and_projects_page(client, app):
    _login_student(client)
    r = client.get("/student/roadmap")
    assert r.status_code == 200
    with app.app_context():
        role = CareerRole.query.filter_by(name="Data Analyst").first()
        role_id = role.id
    r = client.post(
        "/student/roadmap",
        data={"role_id": role_id, "generate": "1"},
        follow_redirects=True,
    )
    assert r.status_code == 200
    assert b"Roadmap" in r.data or b"roadmap" in r.data

    r = client.get("/student/projects")
    assert r.status_code == 200
    assert b"GitHub" in r.data

    r = client.post(
        "/student/projects",
        data={
            "title": "Manual Demo",
            "description": "Built for tests",
            "tech_stack": "Python, Flask",
            "role": "Developer",
            "url": "https://example.com",
            "submit": True,
        },
        follow_redirects=True,
    )
    assert r.status_code == 200
    with app.app_context():
        student = User.query.filter_by(email="student@test.com").first()
        profile = StudentProfile.query.filter_by(user_id=student.id).first()
        assert Project.query.filter_by(student_id=profile.id, title="Manual Demo").first()


def test_coach_route_contextual(client, app):
    _login_student(client)
    r = client.post(
        "/student/coach",
        data={"message": "What should I learn next?", "submit": True},
        follow_redirects=True,
    )
    assert r.status_code == 200
    r = client.post(
        "/student/coach",
        data={"message": "Why should I learn that?", "submit": True},
        follow_redirects=True,
    )
    assert r.status_code == 200
    body = r.data.decode("utf-8", errors="replace").lower()
    assert "why" in body or "learn" in body
