"""Mock interview sessions, questions, and answers."""

from datetime import datetime, timezone

from app.extensions import db


class InterviewSession(db.Model):
    __tablename__ = "interview_sessions"

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(
        db.Integer, db.ForeignKey("student_profiles.id"), nullable=False, index=True
    )
    interview_type = db.Column(db.String(64), nullable=False, default="behavioral")
    role_focus = db.Column(db.String(160), nullable=True)
    status = db.Column(db.String(32), nullable=False, default="in_progress")
    overall_score = db.Column(db.Float, nullable=True)
    summary = db.Column(db.Text, nullable=True)
    started_at = db.Column(
        db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    completed_at = db.Column(db.DateTime, nullable=True)

    student = db.relationship("StudentProfile", back_populates="interview_sessions")
    questions = db.relationship(
        "InterviewQuestion",
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="InterviewQuestion.order_index",
        lazy="joined",
    )

    def __repr__(self) -> str:
        return f"<InterviewSession id={self.id} type={self.interview_type!r}>"


class InterviewQuestion(db.Model):
    __tablename__ = "interview_questions"

    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(
        db.Integer, db.ForeignKey("interview_sessions.id"), nullable=False, index=True
    )
    order_index = db.Column(db.Integer, nullable=False, default=0)
    question_type = db.Column(db.String(64), nullable=False, default="behavioral")
    prompt = db.Column(db.Text, nullable=False)
    expected_keywords = db.Column(db.Text, nullable=True)  # comma-separated or JSON

    session = db.relationship("InterviewSession", back_populates="questions")
    answer = db.relationship(
        "InterviewAnswer",
        back_populates="question",
        uselist=False,
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<InterviewQuestion id={self.id} session={self.session_id}>"


class InterviewAnswer(db.Model):
    __tablename__ = "interview_answers"

    id = db.Column(db.Integer, primary_key=True)
    question_id = db.Column(
        db.Integer,
        db.ForeignKey("interview_questions.id"),
        unique=True,
        nullable=False,
        index=True,
    )
    answer_text = db.Column(db.Text, nullable=False, default="")
    score = db.Column(db.Float, nullable=True)
    feedback = db.Column(db.Text, nullable=True)
    keyword_coverage = db.Column(db.Float, nullable=True)
    evaluated_at = db.Column(
        db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    question = db.relationship("InterviewQuestion", back_populates="answer")

    def __repr__(self) -> str:
        return f"<InterviewAnswer id={self.id} question={self.question_id}>"
