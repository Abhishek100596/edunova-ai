"""
Idempotent EDUNOVA demo catalog + rich demo profile seeder.

Safe to run repeatedly. Does not delete unrelated user accounts.
Resets known demo/admin account passwords to documented defaults.

Usage:
  python scripts/seed_demo_data.py
  python scripts/seed.py   # thin wrapper calling the same entrypoint
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.demo_catalog import (  # noqa: E402
    CAREER_ROLES,
    COMPANIES,
    ROLE_SKILLS,
    ROADMAP_TEMPLATES,
    SKILLS,
)


def _slugify(name: str) -> str:
    slug = "".join(ch.lower() if ch.isalnum() else "-" for ch in name).strip("-")
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug or "item"


def ensure_extra_columns(db) -> None:
    """Best-effort SQLite ALTER for newly added columns (create_all won't alter)."""
    from sqlalchemy import text

    statements = [
        "ALTER TABLE skills ADD COLUMN description TEXT",
        "ALTER TABLE skills ADD COLUMN difficulty VARCHAR(40)",
        "ALTER TABLE skills ADD COLUMN demand_indicator VARCHAR(40)",
        "ALTER TABLE companies ADD COLUMN industry VARCHAR(120)",
        "ALTER TABLE companies ADD COLUMN headquarters VARCHAR(160)",
        "ALTER TABLE companies ADD COLUMN description TEXT",
        "ALTER TABLE companies ADD COLUMN competitiveness VARCHAR(40)",
        "ALTER TABLE user_targets ADD COLUMN company_name VARCHAR(160)",
        "ALTER TABLE user_targets ADD COLUMN target_role VARCHAR(160)",
        "ALTER TABLE user_targets ADD COLUMN status VARCHAR(40)",
        "ALTER TABLE user_targets ADD COLUMN notes TEXT",
    ]
    for stmt in statements:
        try:
            db.session.execute(text(stmt))
            db.session.commit()
        except Exception:
            db.session.rollback()


def seed_skills(db, Skill):
    print("Seeding skills…")
    for row in SKILLS:
        skill = Skill.query.filter_by(name=row["name"]).first()
        if skill is None:
            skill = Skill(name=row["name"], category=row["category"])
            db.session.add(skill)
        skill.category = row["category"]
        skill.difficulty = row.get("difficulty")
        skill.demand_indicator = row.get("demand_indicator")
        skill.description = (
            skill.description
            or f"{row['name']} — catalog skill for career matching ({row['category']})."
        )
    db.session.commit()
    print(f"  {Skill.query.count()} skills")


def seed_roles(db, CareerRole, RoleSkill, Skill):
    print("Seeding career roles…")
    for row in CAREER_ROLES:
        role = CareerRole.query.filter_by(name=row["name"]).first()
        if role is None:
            role = CareerRole(name=row["name"], category=row["category"])
            db.session.add(role)
        role.category = row["category"]
        role.description = row.get("description")
    db.session.commit()

    for role_name, reqs in ROLE_SKILLS.items():
        role = CareerRole.query.filter_by(name=role_name).first()
        if role is None:
            continue
        for req in reqs:
            skill = Skill.query.filter_by(name=req["skill"]).first()
            if skill is None:
                continue
            link = RoleSkill.query.filter_by(role_id=role.id, skill_id=skill.id).first()
            if link is None:
                link = RoleSkill(role_id=role.id, skill_id=skill.id)
                db.session.add(link)
            link.required_level = int(req["required_level"])
            link.importance = float(req["importance"])
    db.session.commit()
    print(f"  {CareerRole.query.count()} roles")


def seed_companies(db, Company):
    print("Seeding companies…")
    for row in COMPANIES:
        slug = row.get("slug") or _slugify(row["name"])
        company = Company.query.filter_by(slug=slug).first()
        if company is None:
            company = Company.query.filter_by(name=row["name"]).first()
        if company is None:
            company = Company(name=row["name"], slug=slug)
            db.session.add(company)
        company.name = row["name"]
        company.slug = slug
        company.company_type = row.get("company_type") or "product"
        company.industry = row.get("industry")
        company.headquarters = row.get("headquarters")
        company.description = row.get("description")
        company.competitiveness = row.get("competitiveness")
        company.country_focus = row.get("country_focus")
        if not company.careers_url:
            # Public homepage placeholder — not claimed as live JD evidence
            company.website = company.website or f"https://www.google.com/search?q={row['name'].replace(' ', '+')}+careers"
            company.notes = (
                (company.notes or "")
                + " Demo catalog entry. Verify requirements via official careers pages."
            ).strip()
    db.session.commit()
    print(f"  {Company.query.count()} companies")


def seed_company_requirements(db, Company, CareerRole, Skill, CompanyRoleRequirement, EvidenceSource):
    print("Seeding sample company role requirements…")
    # Attach light evidence + requirements for major firms × analyst/engineer roles
    evidence = EvidenceSource.query.filter_by(title="O*NET OnLine (public)").first()
    if evidence is None:
        evidence = EvidenceSource(
            title="O*NET OnLine (public)",
            url="https://www.onetonline.org/",
            source_type="onet",
            publisher="U.S. Department of Labor / ETA",
            is_official=True,
            verification_status="verified",
            confidence=0.8,
            last_verified_at=datetime.now(timezone.utc),
            notes="Public occupational framework — not company-specific hiring guarantees.",
        )
        db.session.add(evidence)
        db.session.commit()

    focus_companies = [
        "Microsoft",
        "Google",
        "Amazon",
        "TCS",
        "Infosys",
        "Accenture",
        "IBM",
        "Deloitte",
        "NVIDIA",
        "Zoho",
    ]
    focus_roles = ["Data Analyst", "Software Engineer", "Data Scientist", "Machine Learning Engineer"]
    skill_sets = {
        "Data Analyst": ["Python", "SQL", "Excel", "Power BI"],
        "Software Engineer": ["Python", "DSA", "SQL", "Git"],
        "Data Scientist": ["Python", "Machine Learning", "Statistics", "SQL"],
        "Machine Learning Engineer": ["Python", "Machine Learning", "Docker", "REST APIs"],
    }
    upserted = 0
    for cname in focus_companies:
        company = Company.query.filter_by(name=cname).first()
        if company is None:
            continue
        for rname in focus_roles:
            role = CareerRole.query.filter_by(name=rname).first()
            if role is None:
                continue
            for sname in skill_sets.get(rname, []):
                skill = Skill.query.filter_by(name=sname).first()
                if skill is None:
                    continue
                existing = CompanyRoleRequirement.query.filter_by(
                    company_id=company.id,
                    career_role_id=role.id,
                    skill_id=skill.id,
                ).first()
                if existing is None:
                    existing = CompanyRoleRequirement(
                        company_id=company.id,
                        career_role_id=role.id,
                        skill_id=skill.id,
                    )
                    db.session.add(existing)
                    upserted += 1
                existing.required_level = 3
                existing.importance = "important"
                existing.requirement_text = (
                    f"Catalog signal: {sname} commonly relevant for {rname}-style roles. "
                    "Not a live job posting."
                )
                existing.evidence_source_id = evidence.id
                existing.verified_at = datetime.now(timezone.utc)
                existing.status = "active"
    db.session.commit()
    print(f"  {upserted} requirement rows upserted (plus updates)")


def seed_learning_resources(db, LearningResource, Skill):
    print("Seeding learning resources…")
    resources = [
        ("Python Official Tutorial", "Python Software Foundation", "https://docs.python.org/3/tutorial/", "Python", "official_docs"),
        ("SQLBolt", "SQLBolt", "https://sqlbolt.com/", "SQL", "course"),
        ("pandas User Guide", "pandas", "https://pandas.pydata.org/docs/user_guide/index.html", "Pandas", "official_docs"),
        ("scikit-learn User Guide", "scikit-learn", "https://scikit-learn.org/stable/user_guide.html", "Scikit-learn", "official_docs"),
        ("MDN Web Docs", "MDN", "https://developer.mozilla.org/", "JavaScript", "official_docs"),
        ("Flask Documentation", "Pallets", "https://flask.palletsprojects.com/", "Flask", "official_docs"),
        ("Docker Get Started", "Docker", "https://docs.docker.com/get-started/", "Docker", "official_docs"),
        ("AWS Skill Builder (free catalog)", "Amazon Web Services", "https://skillbuilder.aws/", "AWS", "course"),
        ("O*NET OnLine", "U.S. DOL / ETA", "https://www.onetonline.org/", "Business Analysis", "gov"),
        ("NumPy Documentation", "NumPy", "https://numpy.org/doc/", "NumPy", "official_docs"),
    ]
    for title, provider, url, skill_name, _fmt in resources:
        skill = Skill.query.filter_by(name=skill_name).first()
        row = LearningResource.query.filter_by(url=url).first()
        if row is None:
            row = LearningResource.query.filter_by(title=title).first()
        if row is None:
            row = LearningResource(title=title, url=url)
            db.session.add(row)
        row.provider = provider
        row.url = url
        row.skill_id = skill.id if skill else None
        row.verification_status = "verified"
        row.last_verified_at = datetime.now(timezone.utc)
        row.notes = "Public educational resource. Verify URL freshness periodically."
    db.session.commit()
    print(f"  {LearningResource.query.count()} learning resources")


def seed_accounts(db, User):
    print("Seeding admin + demo accounts…")
    accounts = [
        ("admin@edunova.ai", "Shivendra Admin", "admin", "Admin@123"),
        ("admin@nexora.ai", "EDUNOVA Admin", "admin", "Admin@123"),
        ("demo@edunova.ai", "Shivendra Pratap Singh", "student", "Demo@123"),
        ("demo@nexora.ai", "Shivendra Pratap Singh", "student", "Demo@123"),
    ]
    for email, name, role, password in accounts:
        user = User.query.filter_by(email=email).first()
        if user is None:
            user = User(email=email, name=name, role=role)
            db.session.add(user)
        user.name = name
        user.role = role
        user.set_password(password)
    db.session.commit()
    for email, *_ in accounts:
        print(f"  {email}")


def seed_demo_profile(db, models):
    """Rich coherent Data Analyst–leaning demo profile for Shivendra."""
    (
        User,
        StudentProfile,
        Skill,
        StudentSkill,
        Project,
        Certification,
        Internship,
        CareerRole,
        LearningRoadmap,
        LearningTask,
        ProgressRecord,
        PredictionRecord,
        InterviewSession,
        InterviewQuestion,
        InterviewAnswer,
        Notification,
        Company,
        UserTarget,
    ) = models

    print("Seeding demo student profile…")
    user = User.query.filter_by(email="demo@edunova.ai").first()
    if user is None:
        user = User.query.filter_by(email="demo@nexora.ai").first()
    if user is None:
        print("  skip — no demo user")
        return

    profile = StudentProfile.query.filter_by(user_id=user.id).first()
    if profile is None:
        profile = StudentProfile(user_id=user.id)
        db.session.add(profile)
        db.session.flush()

    profile.college = "University Demo Campus"
    profile.degree = "BCA"
    profile.branch = "Data Science & Artificial Intelligence"
    profile.graduation_year = 2026
    profile.location = "India"
    profile.cgpa = 8.4
    profile.attendance = 92.0
    profile.backlogs = 0
    profile.academic_consistency = 0.88
    profile.onboarding_pct = 100
    profile.preferred_roles = json.dumps(
        ["Data Analyst", "Data Scientist", "Business Analyst"]
    )
    profile.preferred_industries = json.dumps(
        ["Technology", "Analytics", "Fintech", "IT Services"]
    )
    profile.target_companies = json.dumps(
        ["Microsoft", "Google", "TCS", "Infosys", "Deloitte"]
    )
    profile.preferred_location = "India / Remote"
    profile.higher_studies = False
    db.session.commit()

    demo_skill_levels = {
        "Python": 4,
        "SQL": 3,
        "Pandas": 4,
        "NumPy": 3,
        "Scikit-learn": 3,
        "Excel": 4,
        "Power BI": 3,
        "Tableau": 2,
        "Flask": 3,
        "HTML": 3,
        "CSS": 3,
        "JavaScript": 2,
        "Git": 4,
        "GitHub": 4,
        "C++": 2,
        "Java": 2,
        "Machine Learning": 3,
        "Statistics": 3,
        "Data Visualization": 3,
        "Exploratory Data Analysis": 3,
        "Communication": 3,
        "Problem Solving": 4,
        "REST APIs": 2,
        "Docker": 1,
        "Advanced SQL": 2,
    }
    for name, level in demo_skill_levels.items():
        skill = Skill.query.filter_by(name=name).first()
        if skill is None:
            continue
        link = StudentSkill.query.filter_by(
            student_id=profile.id, skill_id=skill.id
        ).first()
        if link is None:
            link = StudentSkill(student_id=profile.id, skill_id=skill.id)
            db.session.add(link)
        link.level = level
    db.session.commit()

    projects = [
        ("Student Performance Prediction", "Python, Pandas, Scikit-learn", "Predicted academic outcomes using classical ML."),
        ("House Price Prediction", "Python, Scikit-learn, NumPy", "Regression model for housing prices with feature analysis."),
        ("Smart Hire AI", "Python, Flask, ML", "Hiring-readiness analytics prototype for academic demo."),
        ("Eventify", "HTML, CSS, JavaScript", "Event discovery web UI project."),
        ("EduNova AI", "Python, Flask, SQL", "Education, skill and career intelligence platform."),
        ("Nexus AI", "Kotlin, Android", "Separate Android voice assistant project (portfolio mention)."),
    ]
    if Project.query.filter_by(student_id=profile.id).count() == 0:
        for title, stack, desc in projects:
            db.session.add(
                Project(
                    student_id=profile.id,
                    title=title,
                    tech_stack=stack,
                    description=desc,
                )
            )
        db.session.commit()

    if Certification.query.filter_by(student_id=profile.id).count() == 0:
        db.session.add_all(
            [
                Certification(
                    student_id=profile.id,
                    name="Python for Data Science",
                    issuer="Demo Learning Provider",
                ),
                Certification(
                    student_id=profile.id,
                    name="SQL Fundamentals",
                    issuer="Demo Learning Provider",
                ),
            ]
        )
        db.session.commit()

    if Internship.query.filter_by(student_id=profile.id).count() == 0:
        db.session.add(
            Internship(
                student_id=profile.id,
                title="Data Analyst Intern",
                company="Demo Analytics Lab",
                description="Supported dashboards, Excel analysis, and SQL reporting.",
            )
        )
        db.session.commit()

    # Demo readiness history (labelled via notes in ProgressRecord metric_name)
    if ProgressRecord.query.filter_by(student_id=profile.id).count() < 4:
        base = datetime.now(timezone.utc) - timedelta(days=28)
        for i, score in enumerate([54.0, 59.0, 64.0, 71.0]):
            db.session.add(
                ProgressRecord(
                    student_id=profile.id,
                    metric_name="readiness_demo_history",
                    metric_value=score,
                    recorded_at=base + timedelta(days=7 * i),
                )
            )
        db.session.commit()

    # Roadmap for Data Analyst using template stages if none exists
    role = CareerRole.query.filter_by(name="Data Analyst").first()
    if role and LearningRoadmap.query.filter_by(student_id=profile.id, role_id=role.id).count() == 0:
        stages = ROADMAP_TEMPLATES.get("Data Analyst", [])
        rm = LearningRoadmap(
            student_id=profile.id,
            role_id=role.id,
            title="Roadmap: Data Analyst",
            description="Demo roadmap seeded for viva walkthrough.",
            progress_pct=30.0,
        )
        db.session.add(rm)
        db.session.flush()
        for idx, stage in enumerate(stages, start=1):
            status = "completed" if idx <= 3 else ("in_progress" if idx == 4 else "not_started")
            db.session.add(
                LearningTask(
                    roadmap_id=rm.id,
                    title=stage,
                    description=f"Stage {idx}: {stage}",
                    status=status,
                    order_index=idx,
                    estimated_hours=8.0,
                    completed_at=datetime.now(timezone.utc) if status == "completed" else None,
                )
            )
        db.session.commit()

    # Seed a completed interview sample once
    if InterviewSession.query.filter_by(student_id=profile.id).count() == 0:
        session = InterviewSession(
            student_id=profile.id,
            interview_type="technical",
            role_focus="Data Analyst",
            status="completed",
            overall_score=0.72,
            summary="Demo interview — solid SQL/Python narrative; deepen Advanced SQL.",
            completed_at=datetime.now(timezone.utc),
        )
        db.session.add(session)
        db.session.flush()
        q = InterviewQuestion(
            session_id=session.id,
            prompt="Explain how you would analyze student performance data with SQL and Python.",
            question_type="technical",
            order_index=1,
            expected_keywords=json.dumps(["sql", "python", "join", "aggregate", "visualize"]),
        )
        db.session.add(q)
        db.session.flush()
        db.session.add(
            InterviewAnswer(
                question_id=q.id,
                answer_text="I would clean data in Pandas, join tables in SQL, aggregate metrics, and visualize trends.",
                score=0.75,
                feedback="Good structure. Add measurable outcomes and window functions.",
            )
        )
        db.session.commit()

    # Company tracking targets
    for cname, status in [("Microsoft", "preparing"), ("TCS", "interested"), ("Deloitte", "interested")]:
        company = Company.query.filter_by(name=cname).first()
        if company is None:
            continue
        existing = UserTarget.query.filter_by(
            user_id=user.id, company_id=company.id
        ).first()
        if existing is None:
            existing = UserTarget(user_id=user.id, company_id=company.id)
            db.session.add(existing)
        existing.company_name = cname
        existing.target_role = "Data Analyst"
        existing.status = status
        existing.notes = "Demo tracking entry — compatibility estimate only."
    db.session.commit()

    welcome = Notification.query.filter_by(
        user_id=user.id, title="Welcome to EDUNOVA AI"
    ).first()
    if welcome is None:
        db.session.add(
            Notification(
                user_id=user.id,
                title="Welcome to EDUNOVA AI",
                body="Your demo profile is ready. Explore readiness, careers, companies, and coach.",
                category="system",
            )
        )
        db.session.commit()

    print(f"  demo profile ready for {user.email}")


def needs_demo_seed() -> bool:
    """True when catalog/demo look empty (fresh deploy)."""
    from app.models import Skill, User

    skills = Skill.query.count()
    demo = User.query.filter(
        User.email.in_(["demo@edunova.ai", "demo@nexora.ai"])
    ).first()
    return skills < 40 or demo is None


def seed_into_app() -> dict:
    """Seed catalog/demo inside an existing app context. Idempotent."""
    from app.extensions import db
    from app.models import (
        CareerRole,
        Certification,
        Company,
        CompanyRoleRequirement,
        EvidenceSource,
        Internship,
        InterviewAnswer,
        InterviewQuestion,
        InterviewSession,
        LearningResource,
        LearningRoadmap,
        LearningTask,
        Notification,
        PredictionRecord,
        ProgressRecord,
        Project,
        RoleSkill,
        Skill,
        StudentProfile,
        StudentSkill,
        User,
        UserTarget,
    )

    ensure_extra_columns(db)
    seed_skills(db, Skill)
    seed_roles(db, CareerRole, RoleSkill, Skill)
    seed_companies(db, Company)
    seed_company_requirements(
        db, Company, CareerRole, Skill, CompanyRoleRequirement, EvidenceSource
    )
    seed_learning_resources(db, LearningResource, Skill)
    seed_accounts(db, User)
    seed_demo_profile(
        db,
        (
            User,
            StudentProfile,
            Skill,
            StudentSkill,
            Project,
            Certification,
            Internship,
            CareerRole,
            LearningRoadmap,
            LearningTask,
            ProgressRecord,
            PredictionRecord,
            InterviewSession,
            InterviewQuestion,
            InterviewAnswer,
            Notification,
            Company,
            UserTarget,
        ),
    )
    return {
        "skills": Skill.query.count(),
        "companies": Company.query.count(),
        "roles": CareerRole.query.count(),
    }


def run_seed() -> None:
    from app import create_app
    from app.extensions import db
    from app.models import CareerRole, Company, Skill

    app = create_app()
    with app.app_context():
        db.create_all()
        stats = seed_into_app()
        print("Seed complete (idempotent).")
        print(
            f"Totals → skills={stats['skills']} companies={stats['companies']} "
            f"roles={stats['roles']}"
        )


if __name__ == "__main__":
    run_seed()
