"""EDUNOVA intelligence layer tests — evidence, company fit, what-if, scores."""

from app.models import CareerRole, Company, StudentProfile, User
from app.services.career_switch import analyze_career_switch
from app.services.company_intel import dream_company_analysis, opportunity_fit
from app.services.intelligence_score import compute_intelligence_score
from app.services.skill_confidence import compute_skill_confidence
from app.services.skill_gap import skill_gap_matrix
from app.services.what_if import simulate_extra_projects, simulate_skill_level_change


def test_intelligence_score_deterministic(app):
    with app.app_context():
        student = User.query.filter_by(email="student@test.com").first()
        profile = StudentProfile.query.filter_by(user_id=student.id).first()
        a = compute_intelligence_score(profile)
        b = compute_intelligence_score(profile)
        assert a["overall"] == b["overall"]
        assert 0 <= a["overall"] <= 100
        assert "dimensions" in a


def test_skill_confidence_labels(app):
    with app.app_context():
        student = User.query.filter_by(email="student@test.com").first()
        profile = StudentProfile.query.filter_by(user_id=student.id).first()
        rows = compute_skill_confidence(profile)
        assert isinstance(rows, list)
        assert rows
        assert "confidence" in rows[0]
        assert "label" in rows[0]


def test_skill_gap_matrix(app):
    with app.app_context():
        student = User.query.filter_by(email="student@test.com").first()
        profile = StudentProfile.query.filter_by(user_id=student.id).first()
        role = CareerRole.query.filter_by(name="Data Analyst").first()
        matrix = skill_gap_matrix(profile, role)
        assert matrix["matrix"]
        assert any(r.get("priority") for r in matrix["matrix"])


def test_opportunity_and_dream(app):
    with app.app_context():
        student = User.query.filter_by(email="student@test.com").first()
        profile = StudentProfile.query.filter_by(user_id=student.id).first()
        fits = opportunity_fit(profile)
        assert isinstance(fits, dict)
        assert "opportunities" in fits
        assert "disclaimer" in fits
        company = Company.query.first()
        role = CareerRole.query.first()
        if company and role:
            result = dream_company_analysis(profile, company.id, role.id)
            assert "disclaimer" in result


def test_what_if_does_not_mutate(app):
    with app.app_context():
        student = User.query.filter_by(email="student@test.com").first()
        profile = StudentProfile.query.filter_by(user_id=student.id).first()
        before = compute_intelligence_score(profile)["overall"]
        sim = simulate_skill_level_change(profile, "Python", 5)
        assert sim["label"] == "scenario simulation"
        after = compute_intelligence_score(profile)["overall"]
        assert before == after
        sim2 = simulate_extra_projects(profile, 2)
        assert "disclaimer" in sim2


def test_career_switch(app):
    with app.app_context():
        student = User.query.filter_by(email="student@test.com").first()
        profile = StudentProfile.query.filter_by(user_id=student.id).first()
        role = CareerRole.query.filter_by(name="Data Analyst").first()
        result = analyze_career_switch(
            profile, current_role_id=None, target_role_id=role.id
        )
        assert "transition_plan" in result
        assert "disclaimer" in result


def test_new_intelligence_routes_require_login(client):
    for path in (
        "/student/companies",
        "/student/opportunity-fit",
        "/student/dream-company",
        "/student/what-if",
        "/student/intelligence-score",
        "/student/career-switch",
    ):
        r = client.get(path, follow_redirects=False)
        assert r.status_code in (302, 401)
