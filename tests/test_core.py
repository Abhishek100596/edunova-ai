"""Core EDUNOVA AI tests — auth, authorization, ML prediction, skill-gap, resume matching."""

from app.models import CareerRole, StudentProfile, User
from app.services.career import match_roles
from app.services.placement import predict_placement
from app.services.resume_intel import tfidf_cosine_match
from app.services.skill_gap import gaps_for_role_id


def test_landing(client):
    r = client.get("/")
    assert r.status_code == 200
    assert b"EDUNOVA" in r.data


def test_register_login_logout(client, app):
    r = client.post(
        "/register",
        data={
            "name": "New User",
            "email": "new@test.com",
            "password": "Secure@123",
            "confirm": "Secure@123",
            "submit": True,
        },
        follow_redirects=True,
    )
    assert r.status_code == 200
    with app.app_context():
        u = User.query.filter_by(email="new@test.com").first()
        assert u is not None
        assert u.check_password("Secure@123")
        assert u.password_hash != "Secure@123"

    r = client.post(
        "/login",
        data={"email": "new@test.com", "password": "Secure@123", "submit": True},
        follow_redirects=True,
    )
    assert r.status_code == 200
    r = client.get("/logout", follow_redirects=True)
    assert r.status_code == 200


def test_student_cannot_access_admin(client):
    client.post(
        "/login",
        data={"email": "student@test.com", "password": "Student@123", "submit": True},
        follow_redirects=True,
    )
    r = client.get("/admin/dashboard", follow_redirects=False)
    assert r.status_code in (302, 403)


def test_admin_can_access_admin(client):
    client.post(
        "/login",
        data={"email": "admin@test.com", "password": "Admin@123", "submit": True},
        follow_redirects=True,
    )
    r = client.get("/admin/dashboard")
    assert r.status_code == 200


def test_placement_prediction_deterministic(app):
    with app.app_context():
        student = User.query.filter_by(email="student@test.com").first()
        profile = StudentProfile.query.filter_by(user_id=student.id).first()
        result = predict_placement(profile)
        assert "probability" in result
        assert 0 <= float(result["probability"]) <= 1
        assert "readiness" in result
        assert "factors_positive" in result
        assert "factors_negative" in result


def test_career_and_skill_gap(app):
    with app.app_context():
        student = User.query.filter_by(email="student@test.com").first()
        profile = StudentProfile.query.filter_by(user_id=student.id).first()
        careers = match_roles(profile)
        assert isinstance(careers, list)
        assert len(careers) >= 1
        role = CareerRole.query.filter_by(name="Data Analyst").first()
        gap = gaps_for_role_id(profile, role.id)
        assert gap is not None


def test_jd_compatibility_tfidf():
    resume = "Experienced in Python and Excel. Built a sales dashboard."
    jd = "Looking for Python, SQL, Power BI skills."
    score = tfidf_cosine_match(resume, jd)
    assert 0.0 <= float(score) <= 1.0


def test_api_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
