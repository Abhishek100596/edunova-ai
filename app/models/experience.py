"""Projects, certifications, and internships."""

import json
from datetime import datetime, timezone

from app.extensions import db


class Project(db.Model):
    __tablename__ = "projects"

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(
        db.Integer, db.ForeignKey("student_profiles.id"), nullable=False, index=True
    )
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=True)
    tech_stack = db.Column(db.String(500), nullable=True)
    role = db.Column(db.String(120), nullable=True)
    url = db.Column(db.String(500), nullable=True)
    analysis_json = db.Column(db.Text, nullable=True)
    analysis_status = db.Column(db.String(40), nullable=True)
    start_date = db.Column(db.Date, nullable=True)
    end_date = db.Column(db.Date, nullable=True)
    created_at = db.Column(
        db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    student = db.relationship("StudentProfile", back_populates="projects")

    def analysis_dict(self):
        if not self.analysis_json:
            return None
        try:
            return json.loads(self.analysis_json)
        except (TypeError, ValueError):
            return None

    def __repr__(self) -> str:
        return f"<Project id={self.id} title={self.title!r}>"


class Certification(db.Model):
    __tablename__ = "certifications"

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(
        db.Integer, db.ForeignKey("student_profiles.id"), nullable=False, index=True
    )
    name = db.Column(db.String(200), nullable=False)
    issuer = db.Column(db.String(200), nullable=True)
    credential_id = db.Column(db.String(120), nullable=True)
    url = db.Column(db.String(500), nullable=True)
    issue_date = db.Column(db.Date, nullable=True)
    expiry_date = db.Column(db.Date, nullable=True)
    created_at = db.Column(
        db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    student = db.relationship("StudentProfile", back_populates="certifications")

    def __repr__(self) -> str:
        return f"<Certification id={self.id} name={self.name!r}>"


class Internship(db.Model):
    __tablename__ = "internships"

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(
        db.Integer, db.ForeignKey("student_profiles.id"), nullable=False, index=True
    )
    company = db.Column(db.String(200), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=True)
    location = db.Column(db.String(120), nullable=True)
    start_date = db.Column(db.Date, nullable=True)
    end_date = db.Column(db.Date, nullable=True)
    is_current = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(
        db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    student = db.relationship("StudentProfile", back_populates="internships")

    def __repr__(self) -> str:
        return f"<Internship id={self.id} company={self.company!r}>"
