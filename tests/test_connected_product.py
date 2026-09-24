"""Regression tests for connected-product reliability repairs."""

from app.extensions import db
from app.models import Certification, Internship, StudentProfile, StudentSkill, User
from app.services import interview as interview_svc
from app.services import what_if


def _login(client):
    return client.post(
        "/login",
        data={"email": "student@test.com", "password": "Student@123", "submit": True},
        follow_redirects=True,
    )


def test_profile_invalid_shows_errors(client):
    _login(client)
    r = client.post(
        "/student/profile",
        data={
            "name": "Student",
            "college": "Test",
            "degree": "B.Tech",
            "branch": "CSE",
            "graduation_year": 1990,  # invalid for form range
            "cgpa": 99,
            "attendance": 90,
            "backlogs": 0,
            "academic_consistency": 0.8,
            "submit": True,
        },
        follow_redirects=True,
    )
    assert r.status_code == 200
    body = r.data.decode("utf-8", errors="replace").lower()
    assert "please fix" in body or "invalid" in body or "between" in body


def test_skill_remove_is_post_only(client, app):
    _login(client)
    with app.app_context():
        student = User.query.filter_by(email="student@test.com").first()
        profile = StudentProfile.query.filter_by(user_id=student.id).first()
        link = StudentSkill.query.filter_by(student_id=profile.id).first()
        sid = link.skill_id
    # GET must not delete
    r = client.get(f"/student/profile?remove_skill={sid}", follow_redirects=True)
    assert r.status_code == 200
    with app.app_context():
        assert StudentSkill.query.filter_by(student_id=profile.id, skill_id=sid).first()
    # POST removes
    r = client.post(
        "/student/profile",
        data={"remove_skill": "1", "skill_id": sid},
        follow_redirects=True,
    )
    assert r.status_code == 200
    with app.app_context():
        assert StudentSkill.query.filter_by(student_id=profile.id, skill_id=sid).first() is None


def test_add_cert_and_internship(client, app):
    _login(client)
    r = client.post(
        "/student/projects",
        data={
            "name": "AWS Cloud Practitioner",
            "issuer": "Amazon",
            "add_cert": "1",
            "submit": True,
        },
        follow_redirects=True,
    )
    assert r.status_code == 200
    r = client.post(
        "/student/projects",
        data={
            "company": "Acme Labs",
            "title": "Data Intern",
            "description": "Built dashboards",
            "add_intern": "1",
            "submit": True,
        },
        follow_redirects=True,
    )
    assert r.status_code == 200
    with app.app_context():
        student = User.query.filter_by(email="student@test.com").first()
        profile = StudentProfile.query.filter_by(user_id=student.id).first()
        assert Certification.query.filter_by(student_id=profile.id).count() >= 1
        assert Internship.query.filter_by(student_id=profile.id).count() >= 1


def test_interview_cannot_complete_early(app):
    with app.app_context():
        student = User.query.filter_by(email="student@test.com").first()
        profile = StudentProfile.query.filter_by(user_id=student.id).first()
        sess = interview_svc.start_session(profile, "behavioral", role_focus="Analyst")
        import pytest

        with pytest.raises(ValueError, match="Answer all"):
            interview_svc.complete_session(sess.id, student_id=profile.id)


def test_what_if_cgpa_non_mutating(app):
    with app.app_context():
        student = User.query.filter_by(email="student@test.com").first()
        profile = StudentProfile.query.filter_by(user_id=student.id).first()
        before = profile.cgpa
        result = what_if.simulate_cgpa_change(profile, 9.5)
        assert result["scenario"] == "cgpa_change"
        assert result["simulated"]["overall_readiness"] is not None
        db.session.refresh(profile)
        assert profile.cgpa == before
