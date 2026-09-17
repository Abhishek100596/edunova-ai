"""Generate and update learning roadmaps from skill gaps."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.extensions import db
from app.models.learning import TASK_STATUSES, LearningRoadmap, LearningTask
from app.models.profile import StudentProfile
from app.models.skills import CareerRole
from app.services.skill_gap import analyze_skill_gaps

STAGE_BUCKETS = (
    ("FOUNDATION", "Build core fundamentals for the target role."),
    ("CORE SKILLS", "Close the highest-priority skill gaps."),
    ("INTERMEDIATE", "Strengthen applied tools and workflows."),
    ("PROJECTS", "Prove skills with portfolio evidence."),
    ("ADVANCED", "Stretch into advanced / differentiating skills."),
    ("INTERVIEW PREPARATION", "Practice explaining your work and role knowledge."),
    ("JOB APPLICATIONS", "Target roles and companies with tailored applications."),
)


def _task_title(skill_name: str, current: int, required: int) -> str:
    if current <= 0:
        return (
            f"Build {skill_name} fundamentals with 5 practice exercises "
            f"and one mini demo (target level {required})"
        )
    if current < required:
        return (
            f"Strengthen {skill_name} from level {current} to {required} "
            f"with applied practice and a portfolio artifact"
        )
    return f"Maintain {skill_name} at level {current} with spaced review"


def _estimated_hours(gap_level: int, importance: float) -> float:
    base = 8.0 * max(1, int(gap_level))
    return round(base * max(0.5, float(importance)), 1)


def _bucket_for_index(i: int, total: int) -> tuple[str, str]:
    if total <= 0:
        return STAGE_BUCKETS[0]
    # Map gap tasks across CORE → ADVANCED; foundation/projects/interview added explicitly.
    ratio = i / max(total - 1, 1)
    if ratio < 0.34:
        return STAGE_BUCKETS[1]
    if ratio < 0.67:
        return STAGE_BUCKETS[2]
    return STAGE_BUCKETS[4]


def generate_roadmap(
    profile: StudentProfile,
    role: CareerRole,
    *,
    replace_existing: bool = False,
) -> LearningRoadmap:
    """
    Create a LearningRoadmap + LearningTask rows from skill gaps for a role.
    Prefaces with role template stages when available.
    """
    analysis = analyze_skill_gaps(profile, role)

    if replace_existing:
        existing = LearningRoadmap.query.filter_by(
            student_id=profile.id, role_id=role.id
        ).all()
        for rm in existing:
            db.session.delete(rm)
        db.session.flush()

    readiness_note = ""
    try:
        from app.utils.readiness import overall_readiness

        readiness_note = f" Current readiness estimate: {overall_readiness(profile):.0f}/100."
    except Exception:  # noqa: BLE001
        readiness_note = ""

    roadmap = LearningRoadmap(
        student_id=profile.id,
        role_id=role.id,
        title=f"Roadmap: {role.name}",
        description=(
            f"Personalized plan for {role.name} from your skill gaps and profile. "
            f"Coverage before plan: {analysis['coverage_pct']}%."
            f"{readiness_note}"
        ),
        progress_pct=0.0,
    )
    db.session.add(roadmap)
    db.session.flush()

    order = 0

    def _add_task(
        *,
        title: str,
        description: str,
        skill_id: int | None = None,
        hours: float = 8.0,
        stage: str | None = None,
    ) -> None:
        nonlocal order
        order += 1
        stage_prefix = f"[{stage}] " if stage else ""
        db.session.add(
            LearningTask(
                roadmap_id=roadmap.id,
                skill_id=skill_id,
                title=f"{stage_prefix}{title}"[:200],
                description=description,
                status="not_started",
                order_index=order,
                estimated_hours=hours,
            )
        )

    # FOUNDATION
    _add_task(
        title=f"Confirm target role: {role.name}",
        description=(
            STAGE_BUCKETS[0][1]
            + f" Review role expectations and your preferred industries/locations on your profile."
        ),
        hours=3.0,
        stage="FOUNDATION",
    )

    # Role curriculum stages (when catalog has a template)
    try:
        from scripts.demo_catalog import ROADMAP_TEMPLATES

        stages = ROADMAP_TEMPLATES.get(role.name) or []
    except Exception:  # noqa: BLE001
        stages = []
    for stage in stages:
        _add_task(
            title=stage,
            description=f"Curriculum stage for {role.name}: {stage}",
            hours=8.0,
            stage="CORE SKILLS",
        )

    gaps = list(analysis.get("gaps") or [])
    for idx, gap in enumerate(gaps):
        stage_name, stage_blurb = _bucket_for_index(idx, len(gaps))
        _add_task(
            title=_task_title(
                gap["skill_name"], gap["current_level"], gap["required_level"]
            ),
            description=(
                f"{stage_blurb} Status: {gap['status']}. Need level {gap['required_level']}, "
                f"currently {gap['current_level']} (gap {gap['gap_level']})."
            ),
            skill_id=gap["skill_id"],
            hours=_estimated_hours(gap["gap_level"], gap["importance"]),
            stage=stage_name,
        )

    # PROJECTS stage
    project_count = 0
    try:
        from app.models.experience import Project

        project_count = Project.query.filter_by(student_id=profile.id).count()
    except Exception:  # noqa: BLE001
        project_count = 0

    if project_count < 2:
        _add_task(
            title=f"Build a portfolio project that proves readiness for {role.name}",
            description=(
                STAGE_BUCKETS[3][1]
                + " Prefer Flask/SQL or analytics stack evidence: authentication or CRUD, "
                "data validation, and a short README with real outcomes. "
                + (
                    f"You currently have {project_count} project(s) on file."
                    if project_count
                    else "No projects on file yet — add a GitHub analysis in EduNova Projects."
                )
            ),
            hours=20.0,
            stage="PROJECTS",
        )
    else:
        _add_task(
            title=f"Upgrade an existing project for {role.name} storytelling",
            description=(
                STAGE_BUCKETS[3][1]
                + f" You already have {project_count} projects. Improve README metrics, "
                "architecture notes, and interview talking points — do not invent features."
            ),
            hours=12.0,
            stage="PROJECTS",
        )

    # Adaptive: weak interview history → communication practice
    try:
        from app.models.interview import InterviewSession

        past = (
            InterviewSession.query.filter_by(student_id=profile.id, status="completed")
            .order_by(InterviewSession.completed_at.desc())
            .limit(3)
            .all()
        )
        weak_scores = [s.overall_score for s in past if s.overall_score is not None]
        if weak_scores and (sum(weak_scores) / len(weak_scores)) < 65:
            _add_task(
                title="Interview communication drills (STAR + clarity)",
                description=(
                    "Recent mock interview scores suggest communication/structure needs practice. "
                    "Complete 2 timed answers using only real projects on your profile."
                ),
                hours=6.0,
                stage="INTERVIEW PREPARATION",
            )
    except Exception:  # noqa: BLE001
        pass

    # INTERVIEW PREPARATION
    _add_task(
        title=f"Role interview preparation for {role.name}",
        description=(
            STAGE_BUCKETS[5][1]
            + " Use EduNova Interview Prep for technical/HR practice tied to this role."
        ),
        hours=10.0,
        stage="INTERVIEW PREPARATION",
    )

    # JOB APPLICATIONS — grounded in profile preferences / targets when present
    preferred = ""
    try:
        raw_pref = getattr(profile, "preferred_roles", None) or ""
        preferred = str(raw_pref).strip()
    except Exception:  # noqa: BLE001
        preferred = ""
    target_hint = (
        f" Preferred roles on file: {preferred}."
        if preferred and preferred not in {"[]", "null"}
        else " Add preferred roles / target companies in your profile so applications stay specific."
    )
    _add_task(
        title=f"Prepare 5 tailored applications for {role.name}",
        description=(
            STAGE_BUCKETS[6][1]
            + target_hint
            + " Customize resume bullets from real EduNova projects only — do not invent experience."
        ),
        hours=8.0,
        stage="JOB APPLICATIONS",
    )

    if order == 0:
        _add_task(
            title=f"Maintain readiness for {role.name}",
            description="All required skills currently meet or exceed targets.",
            hours=4.0,
            stage="ADVANCED",
        )

    update_roadmap_progress(roadmap)
    db.session.commit()
    return roadmap


def update_roadmap_progress(roadmap: LearningRoadmap) -> float:
    """Recompute progress_pct from task statuses. Returns new percentage."""
    tasks = list(roadmap.tasks or [])
    if not tasks:
        tasks = LearningTask.query.filter_by(roadmap_id=roadmap.id).all()
    if not tasks:
        roadmap.progress_pct = 0.0
        roadmap.updated_at = datetime.now(timezone.utc)
        return 0.0

    weights = {"not_started": 0.0, "in_progress": 0.5, "completed": 1.0}
    total = sum(weights.get(t.status, 0.0) for t in tasks)
    pct = round((total / len(tasks)) * 100.0, 2)
    roadmap.progress_pct = pct
    roadmap.updated_at = datetime.now(timezone.utc)
    return pct


def set_task_status(task_id: int, status: str, *, student_id: int | None = None) -> LearningTask:
    if status not in TASK_STATUSES:
        raise ValueError(
            f"Invalid status {status!r}. Expected one of {TASK_STATUSES}."
        )
    task = db.session.get(LearningTask, task_id)
    if task is None:
        raise ValueError(f"LearningTask id={task_id} not found.")
    if student_id is not None and task.roadmap and task.roadmap.student_id != student_id:
        raise ValueError("Task does not belong to this student.")
    task.status = status
    task.completed_at = (
        datetime.now(timezone.utc) if status == "completed" else None
    )
    update_roadmap_progress(task.roadmap)
    db.session.commit()
    return task


def roadmap_summary(roadmap: LearningRoadmap) -> dict[str, Any]:
    tasks = LearningTask.query.filter_by(roadmap_id=roadmap.id).order_by(
        LearningTask.order_index.asc()
    ).all()
    by_status = {s: 0 for s in TASK_STATUSES}
    stages: dict[str, list[dict[str, Any]]] = {}
    task_rows: list[dict[str, Any]] = []
    for t in tasks:
        by_status[t.status] = by_status.get(t.status, 0) + 1
        stage = "GENERAL"
        title = t.title or ""
        if title.startswith("[") and "]" in title:
            stage = title[1 : title.index("]")]
        row = {
            "id": t.id,
            "title": t.title,
            "description": t.description,
            "skill_id": t.skill_id,
            "status": t.status,
            "order_index": t.order_index,
            "estimated_hours": t.estimated_hours,
            "stage": stage,
        }
        task_rows.append(row)
        stages.setdefault(stage, []).append(row)
    return {
        "roadmap_id": roadmap.id,
        "title": roadmap.title,
        "role_id": roadmap.role_id,
        "progress_pct": roadmap.progress_pct,
        "task_counts": by_status,
        "tasks": task_rows,
        "stages": stages,
    }
