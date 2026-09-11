"""Skills catalog, student skill levels, and career role skill requirements."""

from app.extensions import db


class Skill(db.Model):
    __tablename__ = "skills"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), unique=True, nullable=False, index=True)
    category = db.Column(db.String(80), nullable=False, default="general")
    description = db.Column(db.Text, nullable=True)
    difficulty = db.Column(db.String(40), nullable=True)  # beginner|intermediate|advanced
    demand_indicator = db.Column(db.String(40), nullable=True)  # high|medium|emerging

    student_links = db.relationship(
        "StudentSkill", back_populates="skill", cascade="all, delete-orphan"
    )
    role_links = db.relationship(
        "RoleSkill", back_populates="skill", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Skill id={self.id} name={self.name!r}>"


class StudentSkill(db.Model):
    __tablename__ = "student_skills"
    __table_args__ = (
        db.UniqueConstraint("student_id", "skill_id", name="uq_student_skill"),
    )

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(
        db.Integer, db.ForeignKey("student_profiles.id"), nullable=False, index=True
    )
    skill_id = db.Column(
        db.Integer, db.ForeignKey("skills.id"), nullable=False, index=True
    )
    level = db.Column(db.Integer, nullable=False, default=1)  # 1–5

    student = db.relationship("StudentProfile", back_populates="skills")
    skill = db.relationship("Skill", back_populates="student_links")

    def __repr__(self) -> str:
        return (
            f"<StudentSkill student={self.student_id} "
            f"skill={self.skill_id} level={self.level}>"
        )


class CareerRole(db.Model):
    __tablename__ = "career_roles"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(160), unique=True, nullable=False, index=True)
    description = db.Column(db.Text, nullable=True)
    category = db.Column(db.String(80), nullable=False, default="general")

    required_skills = db.relationship(
        "RoleSkill", back_populates="role", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<CareerRole id={self.id} name={self.name!r}>"


class RoleSkill(db.Model):
    __tablename__ = "role_skills"
    __table_args__ = (
        db.UniqueConstraint("role_id", "skill_id", name="uq_role_skill"),
    )

    id = db.Column(db.Integer, primary_key=True)
    role_id = db.Column(
        db.Integer, db.ForeignKey("career_roles.id"), nullable=False, index=True
    )
    skill_id = db.Column(
        db.Integer, db.ForeignKey("skills.id"), nullable=False, index=True
    )
    required_level = db.Column(db.Integer, nullable=False, default=3)  # 1–5
    importance = db.Column(db.Float, nullable=False, default=1.0)

    role = db.relationship("CareerRole", back_populates="required_skills")
    skill = db.relationship("Skill", back_populates="role_links")

    def __repr__(self) -> str:
        return (
            f"<RoleSkill role={self.role_id} skill={self.skill_id} "
            f"req={self.required_level}>"
        )
