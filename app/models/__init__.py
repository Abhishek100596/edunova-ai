"""Export all SQLAlchemy models for app factory and migrations."""

from app.models.analytics import (
    AIConversation,
    Notification,
    PredictionRecord,
    ProgressRecord,
)
from app.models.experience import Certification, Internship, Project
from app.models.interview import InterviewAnswer, InterviewQuestion, InterviewSession
from app.models.learning import LearningRoadmap, LearningTask
from app.models.profile import StudentProfile
from app.models.research import (
    Company,
    CompanyRoleRequirement,
    DataUpdateLog,
    EvidenceSource,
    LearningResource,
    ResearchSnapshot,
    UserTarget,
)
from app.models.resume import JobDescription, Resume, ResumeAnalysis, ResumeJobMatch
from app.models.skills import CareerRole, RoleSkill, Skill, StudentSkill
from app.models.user import User

__all__ = [
    "User",
    "StudentProfile",
    "Skill",
    "StudentSkill",
    "CareerRole",
    "RoleSkill",
    "Project",
    "Certification",
    "Internship",
    "Resume",
    "ResumeAnalysis",
    "JobDescription",
    "ResumeJobMatch",
    "InterviewSession",
    "InterviewQuestion",
    "InterviewAnswer",
    "LearningRoadmap",
    "LearningTask",
    "PredictionRecord",
    "ProgressRecord",
    "AIConversation",
    "Notification",
    "EvidenceSource",
    "Company",
    "CompanyRoleRequirement",
    "LearningResource",
    "ResearchSnapshot",
    "DataUpdateLog",
    "UserTarget",
]
