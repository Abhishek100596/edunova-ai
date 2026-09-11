"""Research evidence, company intel, learning resources, and user targets."""

from datetime import datetime, timezone

from app.extensions import db

EVIDENCE_SOURCE_TYPES = (
    "official_careers",
    "gov",
    "onet",
    "bls",
    "docs",
    "other",
)
VERIFICATION_STATUSES = ("verified", "needs_review", "stale", "unverified")
COMPANY_TYPES = ("product", "service", "consulting")
REQUIREMENT_IMPORTANCE = ("core", "important", "supporting", "nice")


class EvidenceSource(db.Model):
    __tablename__ = "evidence_sources"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255), nullable=False)
    url = db.Column(db.String(500), nullable=True)
    source_type = db.Column(db.String(40), nullable=False, default="other")
    publisher = db.Column(db.String(200), nullable=True)
    is_official = db.Column(db.Boolean, nullable=False, default=False)
    published_date = db.Column(db.String(40), nullable=True)
    accessed_at = db.Column(
        db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    jurisdiction = db.Column(db.String(80), nullable=True)
    role_category = db.Column(db.String(80), nullable=True)
    excerpt = db.Column(db.Text, nullable=True)
    verification_status = db.Column(
        db.String(32), nullable=False, default="unverified"
    )
    confidence = db.Column(db.Float, nullable=False, default=0.0)
    last_verified_at = db.Column(db.DateTime, nullable=True)
    source_priority = db.Column(db.Integer, nullable=False, default=50)
    notes = db.Column(db.Text, nullable=True)

    role_requirements = db.relationship(
        "CompanyRoleRequirement", back_populates="evidence_source"
    )

    def __repr__(self) -> str:
        return f"<EvidenceSource id={self.id} title={self.title!r}>"


class Company(db.Model):
    __tablename__ = "companies"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(160), unique=True, nullable=False, index=True)
    slug = db.Column(db.String(160), unique=True, nullable=False, index=True)
    company_type = db.Column(db.String(40), nullable=False, default="product")
    industry = db.Column(db.String(120), nullable=True)
    headquarters = db.Column(db.String(160), nullable=True)
    description = db.Column(db.Text, nullable=True)
    competitiveness = db.Column(db.String(40), nullable=True)  # high|medium|moderate
    website = db.Column(db.String(500), nullable=True)
    careers_url = db.Column(db.String(500), nullable=True)
    country_focus = db.Column(db.String(120), nullable=True)
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(
        db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    role_requirements = db.relationship(
        "CompanyRoleRequirement",
        back_populates="company",
        cascade="all, delete-orphan",
    )
    targets = db.relationship("UserTarget", back_populates="company")

    def __repr__(self) -> str:
        return f"<Company id={self.id} name={self.name!r}>"


class CompanyRoleRequirement(db.Model):
    __tablename__ = "company_role_requirements"

    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(
        db.Integer, db.ForeignKey("companies.id"), nullable=False, index=True
    )
    career_role_id = db.Column(
        db.Integer, db.ForeignKey("career_roles.id"), nullable=False, index=True
    )
    title = db.Column(db.String(200), nullable=True)
    location = db.Column(db.String(120), nullable=True)
    seniority = db.Column(db.String(80), nullable=True)
    skill_id = db.Column(
        db.Integer, db.ForeignKey("skills.id"), nullable=True, index=True
    )
    required_level = db.Column(db.Integer, nullable=False, default=3)  # 1–5
    importance = db.Column(db.String(32), nullable=False, default="important")
    requirement_text = db.Column(db.Text, nullable=True)
    evidence_source_id = db.Column(
        db.Integer, db.ForeignKey("evidence_sources.id"), nullable=True, index=True
    )
    verified_at = db.Column(db.DateTime, nullable=True)
    status = db.Column(db.String(32), nullable=False, default="active")

    company = db.relationship("Company", back_populates="role_requirements")
    career_role = db.relationship("CareerRole")
    skill = db.relationship("Skill")
    evidence_source = db.relationship(
        "EvidenceSource", back_populates="role_requirements"
    )

    def __repr__(self) -> str:
        return (
            f"<CompanyRoleRequirement id={self.id} "
            f"company={self.company_id} role={self.career_role_id}>"
        )


class LearningResource(db.Model):
    __tablename__ = "learning_resources"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255), nullable=False)
    provider = db.Column(db.String(160), nullable=True)
    url = db.Column(db.String(500), nullable=True)
    topic = db.Column(db.String(160), nullable=True)
    skill_id = db.Column(
        db.Integer, db.ForeignKey("skills.id"), nullable=True, index=True
    )
    level = db.Column(db.String(40), nullable=True)
    format = db.Column(db.String(40), nullable=True)
    estimated_hours = db.Column(db.Float, nullable=True)
    verification_status = db.Column(
        db.String(32), nullable=False, default="unverified"
    )
    last_verified_at = db.Column(db.DateTime, nullable=True)
    notes = db.Column(db.Text, nullable=True)

    skill = db.relationship("Skill")

    def __repr__(self) -> str:
        return f"<LearningResource id={self.id} title={self.title!r}>"


class ResearchSnapshot(db.Model):
    __tablename__ = "research_snapshots"

    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(160), nullable=False, index=True)
    payload_json = db.Column(db.Text, nullable=False, default="{}")
    created_at = db.Column(
        db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    def __repr__(self) -> str:
        return f"<ResearchSnapshot id={self.id} key={self.key!r}>"


class DataUpdateLog(db.Model):
    __tablename__ = "data_update_logs"

    id = db.Column(db.Integer, primary_key=True)
    entity_type = db.Column(db.String(80), nullable=False)
    entity_id = db.Column(db.Integer, nullable=True)
    action = db.Column(db.String(80), nullable=False)
    note = db.Column(db.Text, nullable=True)
    created_at = db.Column(
        db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    def __repr__(self) -> str:
        return (
            f"<DataUpdateLog id={self.id} "
            f"entity={self.entity_type!r} action={self.action!r}>"
        )


class UserTarget(db.Model):
    """Dream company / role selection / personal company tracking for a student."""

    __tablename__ = "user_targets"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=False, index=True
    )
    company_id = db.Column(
        db.Integer, db.ForeignKey("companies.id"), nullable=True, index=True
    )
    career_role_id = db.Column(
        db.Integer, db.ForeignKey("career_roles.id"), nullable=True, index=True
    )
    company_name = db.Column(db.String(160), nullable=True)  # custom / override label
    target_role = db.Column(db.String(160), nullable=True)
    experience_level = db.Column(db.String(80), nullable=True)
    location = db.Column(db.String(120), nullable=True)
    status = db.Column(
        db.String(40), nullable=False, default="interested"
    )  # interested|preparing|applied|interview|selected|rejected
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(
        db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    user = db.relationship("User")
    company = db.relationship("Company", back_populates="targets")
    career_role = db.relationship("CareerRole")

    def __repr__(self) -> str:
        return (
            f"<UserTarget id={self.id} user={self.user_id} "
            f"company={self.company_id} role={self.career_role_id}>"
        )
