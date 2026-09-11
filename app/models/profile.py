"""Student profile linked 1:1 to a user."""

from datetime import datetime, timezone

from app.extensions import db


class StudentProfile(db.Model):
    __tablename__ = "student_profiles"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), unique=True, nullable=False, index=True
    )

    college = db.Column(db.String(255), nullable=True)
    degree = db.Column(db.String(120), nullable=True)
    branch = db.Column(db.String(120), nullable=True)
    graduation_year = db.Column(db.Integer, nullable=True)
    location = db.Column(db.String(120), nullable=True)
    age = db.Column(db.Integer, nullable=True)

    cgpa = db.Column(db.Float, nullable=True)
    attendance = db.Column(db.Float, nullable=True)
    backlogs = db.Column(db.Integer, nullable=False, default=0)
    academic_consistency = db.Column(db.Float, nullable=True)

    preferred_roles = db.Column(db.Text, nullable=True)  # JSON list as text
    preferred_industries = db.Column(db.Text, nullable=True)
    target_companies = db.Column(db.Text, nullable=True)
    preferred_location = db.Column(db.String(120), nullable=True)
    higher_studies = db.Column(db.Boolean, nullable=False, default=False)

    onboarding_pct = db.Column(db.Integer, nullable=False, default=0)
    theme_preference = db.Column(db.String(32), nullable=False, default="system")

    created_at = db.Column(
        db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    user = db.relationship("User", back_populates="profile")
    skills = db.relationship(
        "StudentSkill",
        back_populates="student",
        cascade="all, delete-orphan",
        lazy="dynamic",
    )
    projects = db.relationship(
        "Project",
        back_populates="student",
        cascade="all, delete-orphan",
        lazy="dynamic",
    )
    certifications = db.relationship(
        "Certification",
        back_populates="student",
        cascade="all, delete-orphan",
        lazy="dynamic",
    )
    internships = db.relationship(
        "Internship",
        back_populates="student",
        cascade="all, delete-orphan",
        lazy="dynamic",
    )
    resumes = db.relationship(
        "Resume",
        back_populates="student",
        cascade="all, delete-orphan",
        lazy="dynamic",
    )
    interview_sessions = db.relationship(
        "InterviewSession",
        back_populates="student",
        cascade="all, delete-orphan",
        lazy="dynamic",
    )
    roadmaps = db.relationship(
        "LearningRoadmap",
        back_populates="student",
        cascade="all, delete-orphan",
        lazy="dynamic",
    )

    def __repr__(self) -> str:
        return f"<StudentProfile id={self.id} user_id={self.user_id}>"
