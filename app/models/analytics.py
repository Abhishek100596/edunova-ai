"""Analytics, predictions, AI conversation logs, and notifications."""

from datetime import datetime, timezone

from app.extensions import db


class PredictionRecord(db.Model):
    __tablename__ = "prediction_records"

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(
        db.Integer, db.ForeignKey("student_profiles.id"), nullable=False, index=True
    )
    probability = db.Column(db.Float, nullable=False)
    readiness = db.Column(db.Float, nullable=False)
    factors_positive = db.Column(db.Text, nullable=True)  # JSON
    factors_negative = db.Column(db.Text, nullable=True)  # JSON
    model_meta = db.Column(db.Text, nullable=True)  # JSON
    created_at = db.Column(
        db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    def __repr__(self) -> str:
        return f"<PredictionRecord id={self.id} student={self.student_id}>"


class ProgressRecord(db.Model):
    __tablename__ = "progress_records"

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(
        db.Integer, db.ForeignKey("student_profiles.id"), nullable=False, index=True
    )
    metric_name = db.Column(db.String(80), nullable=False)
    metric_value = db.Column(db.Float, nullable=False)
    snapshot = db.Column(db.Text, nullable=True)  # JSON detail
    recorded_at = db.Column(
        db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    def __repr__(self) -> str:
        return (
            f"<ProgressRecord student={self.student_id} "
            f"{self.metric_name}={self.metric_value}>"
        )


class AIConversation(db.Model):
    __tablename__ = "ai_conversations"

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(
        db.Integer, db.ForeignKey("student_profiles.id"), nullable=False, index=True
    )
    role = db.Column(db.String(32), nullable=False, default="user")  # user|assistant|system
    message = db.Column(db.Text, nullable=False)
    provider = db.Column(db.String(64), nullable=True)
    meta = db.Column(db.Text, nullable=True)  # JSON
    created_at = db.Column(
        db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    def __repr__(self) -> str:
        return f"<AIConversation id={self.id} role={self.role!r}>"


class Notification(db.Model):
    __tablename__ = "notifications"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=False, index=True
    )
    title = db.Column(db.String(200), nullable=False)
    body = db.Column(db.Text, nullable=True)
    category = db.Column(db.String(64), nullable=False, default="info")
    is_read = db.Column(db.Boolean, nullable=False, default=False)
    link = db.Column(db.String(500), nullable=True)
    created_at = db.Column(
        db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    def __repr__(self) -> str:
        return f"<Notification id={self.id} title={self.title!r}>"
