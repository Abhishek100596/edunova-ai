import sys
from pathlib import Path

import pytest

from app import create_app
from app.extensions import db
from app.models import CareerRole, Skill, StudentProfile, StudentSkill, User
from app.models.skills import RoleSkill
from config import TestConfig

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture()
def app():
    application = create_app(TestConfig)
    with application.app_context():
        db.create_all()
        py = Skill(name="Python", category="language")
        sql = Skill(name="SQL", category="database")
        db.session.add_all([py, sql])
        role = CareerRole(
            name="Data Analyst",
            description="Analyze data",
            category="analytics",
        )
        db.session.add(role)
        db.session.commit()
        db.session.add_all(
            [
                RoleSkill(role_id=role.id, skill_id=py.id, required_level=3, importance=1.0),
                RoleSkill(role_id=role.id, skill_id=sql.id, required_level=4, importance=1.2),
            ]
        )
        admin = User(email="admin@test.com", name="Admin", role="admin")
        admin.set_password("Admin@123")
        student = User(email="student@test.com", name="Student", role="student")
        student.set_password("Student@123")
        db.session.add_all([admin, student])
        db.session.commit()
        profile = StudentProfile(
            user_id=student.id,
            college="Test College",
            degree="B.Tech",
            branch="CSE",
            graduation_year=2026,
            cgpa=8.2,
            attendance=90,
            backlogs=0,
            academic_consistency=0.85,
            onboarding_pct=100,
            preferred_roles='["Data Analyst"]',
        )
        db.session.add(profile)
        db.session.commit()
        db.session.add_all(
            [
                StudentSkill(student_id=profile.id, skill_id=py.id, level=4),
                StudentSkill(student_id=profile.id, skill_id=sql.id, level=2),
            ]
        )
        db.session.commit()
        yield application
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()
