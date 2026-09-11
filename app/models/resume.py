"""Resume storage, analysis, job descriptions, and match results."""

from datetime import datetime, timezone

from app.extensions import db


class Resume(db.Model):
    __tablename__ = "resumes"

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(
        db.Integer, db.ForeignKey("student_profiles.id"), nullable=False, index=True
    )
    original_filename = db.Column(db.String(255), nullable=False)
    stored_filename = db.Column(db.String(255), nullable=False)
    file_ext = db.Column(db.String(16), nullable=False)
    parsed_text = db.Column(db.Text, nullable=True)
    uploaded_at = db.Column(
        db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    student = db.relationship("StudentProfile", back_populates="resumes")
    analyses = db.relationship(
        "ResumeAnalysis",
        back_populates="resume",
        cascade="all, delete-orphan",
        lazy="dynamic",
    )
    matches = db.relationship(
        "ResumeJobMatch",
        back_populates="resume",
        cascade="all, delete-orphan",
        lazy="dynamic",
    )

    def __repr__(self) -> str:
        return f"<Resume id={self.id} file={self.original_filename!r}>"


class ResumeAnalysis(db.Model):
    __tablename__ = "resume_analyses"

    id = db.Column(db.Integer, primary_key=True)
    resume_id = db.Column(
        db.Integer, db.ForeignKey("resumes.id"), nullable=False, index=True
    )
    completeness_score = db.Column(db.Float, nullable=False, default=0.0)
    skills_found = db.Column(db.Text, nullable=True)  # JSON list
    sections_present = db.Column(db.Text, nullable=True)  # JSON list
    suggestions = db.Column(db.Text, nullable=True)  # JSON list
    word_count = db.Column(db.Integer, nullable=False, default=0)
    created_at = db.Column(
        db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    resume = db.relationship("Resume", back_populates="analyses")

    def __repr__(self) -> str:
        return f"<ResumeAnalysis id={self.id} resume={self.resume_id}>"


class JobDescription(db.Model):
    __tablename__ = "job_descriptions"

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(
        db.Integer, db.ForeignKey("student_profiles.id"), nullable=True, index=True
    )
    title = db.Column(db.String(200), nullable=False, default="Untitled JD")
    company = db.Column(db.String(200), nullable=True)
    raw_text = db.Column(db.Text, nullable=False)
    created_at = db.Column(
        db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    matches = db.relationship(
        "ResumeJobMatch",
        back_populates="job_description",
        cascade="all, delete-orphan",
        lazy="dynamic",
    )

    def __repr__(self) -> str:
        return f"<JobDescription id={self.id} title={self.title!r}>"


class ResumeJobMatch(db.Model):
    __tablename__ = "resume_job_matches"

    id = db.Column(db.Integer, primary_key=True)
    resume_id = db.Column(
        db.Integer, db.ForeignKey("resumes.id"), nullable=False, index=True
    )
    job_description_id = db.Column(
        db.Integer, db.ForeignKey("job_descriptions.id"), nullable=False, index=True
    )
    match_score = db.Column(db.Float, nullable=False, default=0.0)
    matched_skills = db.Column(db.Text, nullable=True)  # JSON
    missing_skills = db.Column(db.Text, nullable=True)  # JSON
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(
        db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    resume = db.relationship("Resume", back_populates="matches")
    job_description = db.relationship("JobDescription", back_populates="matches")

    def __repr__(self) -> str:
        return (
            f"<ResumeJobMatch resume={self.resume_id} "
            f"jd={self.job_description_id} score={self.match_score}>"
        )
