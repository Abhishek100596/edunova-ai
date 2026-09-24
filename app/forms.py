"""WTForms for EDUNOVA AI auth and student flows."""

from __future__ import annotations

from flask_wtf import FlaskForm
from flask_wtf.file import FileAllowed, FileField, FileRequired
from wtforms import (
    BooleanField,
    FloatField,
    IntegerField,
    PasswordField,
    SelectField,
    StringField,
    SubmitField,
    TextAreaField,
)
from wtforms.validators import (
    DataRequired,
    Email,
    EqualTo,
    Length,
    NumberRange,
    Optional,
    ValidationError,
)

from app.models import User


class RegisterForm(FlaskForm):
    name = StringField("Full name", validators=[DataRequired(), Length(1, 120)])
    email = StringField("Email", validators=[DataRequired(), Email(), Length(1, 255)])
    password = PasswordField(
        "Password", validators=[DataRequired(), Length(8, 128)]
    )
    confirm = PasswordField(
        "Confirm password",
        validators=[DataRequired(), EqualTo("password", message="Passwords must match.")],
    )
    submit = SubmitField("Create account")

    def validate_email(self, field) -> None:
        if User.query.filter_by(email=field.data.strip().lower()).first():
            raise ValidationError("An account with this email already exists.")


class LoginForm(FlaskForm):
    email = StringField("Email", validators=[DataRequired(), Email()])
    password = PasswordField("Password", validators=[DataRequired()])
    remember = BooleanField("Remember me")
    submit = SubmitField("Sign in")


class OnboardingAcademicsForm(FlaskForm):
    college = StringField("College", validators=[Optional(), Length(0, 255)])
    degree = StringField("Degree", validators=[Optional(), Length(0, 120)])
    branch = StringField("Branch", validators=[Optional(), Length(0, 120)])
    graduation_year = IntegerField(
        "Graduation year", validators=[Optional(), NumberRange(2000, 2100)]
    )
    location = StringField("Location", validators=[Optional(), Length(0, 120)])
    age = IntegerField("Age", validators=[Optional(), NumberRange(15, 80)])
    cgpa = FloatField("CGPA", validators=[Optional(), NumberRange(0, 10)])
    attendance = FloatField("Attendance %", validators=[Optional(), NumberRange(0, 100)])
    backlogs = IntegerField("Backlogs", validators=[Optional(), NumberRange(0, 20)])
    academic_consistency = FloatField(
        "Academic consistency (0–1)", validators=[Optional(), NumberRange(0, 1)]
    )
    submit = SubmitField("Save & continue")


class OnboardingPreferencesForm(FlaskForm):
    preferred_roles = StringField(
        "Preferred roles (comma-separated)", validators=[Optional(), Length(0, 500)]
    )
    preferred_industries = StringField(
        "Preferred industries", validators=[Optional(), Length(0, 500)]
    )
    target_companies = StringField(
        "Target companies", validators=[Optional(), Length(0, 500)]
    )
    preferred_location = StringField(
        "Preferred location", validators=[Optional(), Length(0, 120)]
    )
    higher_studies = BooleanField("Considering higher studies")
    submit = SubmitField("Save & continue")


class OnboardingSkillsForm(FlaskForm):
    # skill_ids posted as multi-select; levels as skill_level_<id>
    submit = SubmitField("Finish onboarding")


class ProfileForm(FlaskForm):
    name = StringField("Full name", validators=[DataRequired(), Length(1, 120)])
    college = StringField("College", validators=[Optional(), Length(0, 255)])
    degree = StringField("Degree", validators=[Optional(), Length(0, 120)])
    branch = StringField("Branch", validators=[Optional(), Length(0, 120)])
    graduation_year = IntegerField(
        "Graduation year", validators=[Optional(), NumberRange(2000, 2100)]
    )
    location = StringField("Location", validators=[Optional(), Length(0, 120)])
    age = IntegerField("Age", validators=[Optional(), NumberRange(15, 80)])
    cgpa = FloatField("CGPA", validators=[Optional(), NumberRange(0, 10)])
    attendance = FloatField("Attendance %", validators=[Optional(), NumberRange(0, 100)])
    backlogs = IntegerField("Backlogs", validators=[Optional(), NumberRange(0, 20)])
    academic_consistency = FloatField(
        "Academic consistency (0–1)", validators=[Optional(), NumberRange(0, 1)]
    )
    preferred_roles = StringField("Preferred roles", validators=[Optional(), Length(0, 500)])
    preferred_industries = StringField(
        "Preferred industries", validators=[Optional(), Length(0, 500)]
    )
    target_companies = StringField(
        "Target companies", validators=[Optional(), Length(0, 500)]
    )
    preferred_location = StringField(
        "Preferred location", validators=[Optional(), Length(0, 120)]
    )
    higher_studies = BooleanField("Considering higher studies")
    submit = SubmitField("Save profile")


class ResumeUploadForm(FlaskForm):
    resume = FileField(
        "Resume (PDF or DOCX)",
        validators=[
            FileRequired(),
            FileAllowed(["pdf", "docx"], "PDF or DOCX only."),
        ],
    )
    submit = SubmitField("Upload & analyze")


class JDMatchForm(FlaskForm):
    title = StringField("Job title", validators=[DataRequired(), Length(1, 200)])
    company = StringField("Company", validators=[Optional(), Length(0, 200)])
    raw_text = TextAreaField("Job description", validators=[DataRequired(), Length(20, 20000)])
    resume_id = IntegerField("Resume id", validators=[DataRequired()])
    submit = SubmitField("Match resume")


class InterviewStartForm(FlaskForm):
    interview_type = SelectField(
        "Interview type",
        choices=[
            ("behavioral", "Behavioral"),
            ("technical", "Technical"),
            ("hr", "HR"),
        ],
        validators=[DataRequired()],
    )
    role_focus = StringField("Role focus", validators=[Optional(), Length(0, 160)])
    submit = SubmitField("Start interview")


class InterviewAnswerForm(FlaskForm):
    question_id = IntegerField(validators=[DataRequired()])
    answer_text = TextAreaField("Your answer", validators=[DataRequired(), Length(10, 5000)])
    submit = SubmitField("Submit answer")


class CoachForm(FlaskForm):
    message = TextAreaField("Message", validators=[DataRequired(), Length(2, 4000)])
    submit = SubmitField("Ask coach")


class ProjectForm(FlaskForm):
    title = StringField("Title", validators=[Optional(), Length(0, 200)])
    description = TextAreaField("Description", validators=[Optional(), Length(0, 5000)])
    tech_stack = StringField("Tech stack", validators=[Optional(), Length(0, 500)])
    role = StringField("Your role", validators=[Optional(), Length(0, 120)])
    url = StringField("URL / GitHub", validators=[Optional(), Length(0, 500)])
    submit = SubmitField("Add project")


class GitHubProjectForm(FlaskForm):
    github_url = StringField(
        "GitHub repository URL",
        validators=[DataRequired(), Length(10, 500)],
    )
    role = StringField("Your role (optional)", validators=[Optional(), Length(0, 120)])
    submit = SubmitField("Analyze GitHub project")


class RoadmapGenerateForm(FlaskForm):
    role_id = IntegerField("Role", validators=[DataRequired()])
    submit = SubmitField("Generate roadmap")


class TaskStatusForm(FlaskForm):
    task_id = IntegerField(validators=[DataRequired()])
    status = SelectField(
        choices=[
            ("not_started", "Not started"),
            ("in_progress", "In progress"),
            ("completed", "Completed"),
        ],
        validators=[DataRequired()],
    )
    submit = SubmitField("Update")


class ThemeForm(FlaskForm):
    theme = SelectField(
        choices=[("system", "System"), ("light", "Light"), ("dark", "Dark")],
        validators=[DataRequired()],
    )
    submit = SubmitField("Save theme")


class SkillGapForm(FlaskForm):
    role_id = IntegerField("Role", validators=[DataRequired()])
    submit = SubmitField("Analyze gaps")


class DreamCompanyForm(FlaskForm):
    company_id = IntegerField("Company", validators=[DataRequired()])
    role_id = IntegerField("Target role", validators=[DataRequired()])
    experience_level = StringField(
        "Experience level", validators=[Optional(), Length(0, 80)]
    )
    location = StringField("Preferred location", validators=[Optional(), Length(0, 120)])
    submit = SubmitField("Analyze dream company")


class WhatIfForm(FlaskForm):
    scenario = SelectField(
        "Scenario",
        choices=[
            ("skill_level", "Change a skill level"),
            ("extra_projects", "Add extra projects"),
            ("cgpa", "Improve CGPA"),
            ("extra_internship", "Add an internship"),
            ("extra_certification", "Add a certification"),
        ],
        validators=[DataRequired()],
    )
    skill_name = StringField("Skill name", validators=[Optional(), Length(0, 120)])
    new_level = IntegerField(
        "New skill level (1–5)", validators=[Optional(), NumberRange(1, 5)]
    )
    extra_projects = IntegerField(
        "Extra projects", validators=[Optional(), NumberRange(1, 10)]
    )
    new_cgpa = FloatField(
        "Hypothetical CGPA (0–10)", validators=[Optional(), NumberRange(0, 10)]
    )
    submit = SubmitField("Run simulation")


class CompareCareersForm(FlaskForm):
    role_id_a = IntegerField("Career A", validators=[DataRequired()])
    role_id_b = IntegerField("Career B", validators=[DataRequired()])
    submit = SubmitField("Compare careers")


class CompareCompaniesForm(FlaskForm):
    company_id_a = IntegerField("Company A", validators=[DataRequired()])
    company_id_b = IntegerField("Company B", validators=[DataRequired()])
    submit = SubmitField("Compare companies")


class JDAnalyzerForm(FlaskForm):
    title = StringField("Job title (optional)", validators=[Optional(), Length(0, 200)])
    company = StringField("Company (optional)", validators=[Optional(), Length(0, 200)])
    raw_text = TextAreaField(
        "Paste job description",
        validators=[DataRequired(), Length(40, 30000)],
    )
    submit = SubmitField("Analyze JD")


class CareerSwitchForm(FlaskForm):
    current_role_id = IntegerField("Current role (optional)", validators=[Optional()])
    current_role_label = StringField(
        "Current role label", validators=[Optional(), Length(0, 120)]
    )
    target_role_id = IntegerField("Target role", validators=[DataRequired()])
    submit = SubmitField("Analyze career switch")


class AddStudentSkillForm(FlaskForm):
    skill_name = StringField("Skill name", validators=[DataRequired(), Length(1, 120)])
    category = SelectField(
        "Category",
        choices=[
            ("programming", "Programming"),
            ("data", "Data"),
            ("ai_ml", "AI / ML"),
            ("web", "Web"),
            ("cloud", "Cloud / DevOps"),
            ("professional", "Professional"),
            ("general", "General"),
        ],
        validators=[DataRequired()],
    )
    level = IntegerField(
        "Proficiency (1–5)", validators=[DataRequired(), NumberRange(1, 5)]
    )
    description = TextAreaField("Notes (optional)", validators=[Optional(), Length(0, 1000)])
    submit = SubmitField("Add skill")


class AddTrackedCompanyForm(FlaskForm):
    company_id = IntegerField("Company (catalog)", validators=[Optional()])
    company_name = StringField(
        "Company name", validators=[Optional(), Length(0, 160)]
    )
    target_role = StringField("Target role", validators=[Optional(), Length(0, 160)])
    location = StringField("Location", validators=[Optional(), Length(0, 120)])
    status = SelectField(
        "Status",
        choices=[
            ("interested", "Interested"),
            ("preparing", "Preparing"),
            ("applied", "Applied"),
            ("interview", "Interview"),
            ("selected", "Selected"),
            ("rejected", "Rejected"),
        ],
        validators=[DataRequired()],
    )
    notes = TextAreaField("Notes", validators=[Optional(), Length(0, 2000)])
    submit = SubmitField("Save company")


class CertificationForm(FlaskForm):
    name = StringField("Certification name", validators=[DataRequired(), Length(1, 200)])
    issuer = StringField("Issuer", validators=[Optional(), Length(0, 200)])
    credential_id = StringField("Credential ID", validators=[Optional(), Length(0, 120)])
    url = StringField("URL", validators=[Optional(), Length(0, 500)])
    submit = SubmitField("Add certification")


class InternshipForm(FlaskForm):
    company = StringField("Company", validators=[DataRequired(), Length(1, 200)])
    title = StringField("Role / title", validators=[DataRequired(), Length(1, 200)])
    description = TextAreaField("Description", validators=[Optional(), Length(0, 5000)])
    location = StringField("Location", validators=[Optional(), Length(0, 120)])
    is_current = BooleanField("Currently ongoing")
    submit = SubmitField("Add internship")
