"""Learning roadmaps and tasks derived from skill gaps."""

from datetime import datetime, timezone

from app.extensions import db

TASK_STATUSES = ("not_started", "in_progress", "completed")


class LearningRoadmap(db.Model):
    __tablename__ = "learning_roadmaps"

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(
        db.Integer, db.ForeignKey("student_profiles.id"), nullable=False, index=True
    )
    role_id = db.Column(
        db.Integer, db.ForeignKey("career_roles.id"), nullable=True, index=True
    )
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=True)
    progress_pct = db.Column(db.Float, nullable=False, default=0.0)
    created_at = db.Column(
        db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    student = db.relationship("StudentProfile", back_populates="roadmaps")
    role = db.relationship("CareerRole")
    tasks = db.relationship(
        "LearningTask",
        back_populates="roadmap",
        cascade="all, delete-orphan",
        order_by="LearningTask.order_index",
        lazy="joined",
    )

    def __repr__(self) -> str:
        return f"<LearningRoadmap id={self.id} title={self.title!r}>"


class LearningTask(db.Model):
    __tablename__ = "learning_tasks"

    id = db.Column(db.Integer, primary_key=True)
    roadmap_id = db.Column(
        db.Integer, db.ForeignKey("learning_roadmaps.id"), nullable=False, index=True
    )
    skill_id = db.Column(
        db.Integer, db.ForeignKey("skills.id"), nullable=True, index=True
    )
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(32), nullable=False, default="not_started")
    order_index = db.Column(db.Integer, nullable=False, default=0)
    estimated_hours = db.Column(db.Float, nullable=True)
    completed_at = db.Column(db.DateTime, nullable=True)

    roadmap = db.relationship("LearningRoadmap", back_populates="tasks")
    skill = db.relationship("Skill")

    def __repr__(self) -> str:
        return f"<LearningTask id={self.id} status={self.status!r}>"
