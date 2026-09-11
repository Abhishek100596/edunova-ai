"""Generate and update learning roadmaps from skill gaps."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.extensions import db
from app.models.learning import TASK_STATUSES, LearningRoadmap, LearningTask
from app.models.profile import StudentProfile
from app.models.skills import CareerRole
from app.services.skill_gap import analyze_skill_gaps


def _task_title(skill_name: str, current: int, required: int) -> str:
    if current <= 0:
        return f"Learn fundamentals of {skill_name}"
    return f"Raise {skill_name} from level {current} to {required}"


def _estimated_hours(gap_level: int, importance: float) -> float:
    base = 8.0 * max(1, int(gap_level))
    return round(base * max(0.5, float(importance)), 1)


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

    roadmap = LearningRoadmap(
        student_id=profile.id,
        role_id=role.id,
        title=f"Roadmap: {role.name}",
        description=(
            f"Generated from skill gaps for {role.name}. "
            f"Coverage before plan: {analysis['coverage_pct']}%."
        ),
        progress_pct=0.0,
    )
    db.session.add(roadmap)
    db.session.flush()

    order = 0
    # Role curriculum stages (when catalog has a template)
    try:
        from scripts.demo_catalog import ROADMAP_TEMPLATES

        stages = ROADMAP_TEMPLATES.get(role.name) or []
    except Exception:  # noqa: BLE001
        stages = []
    for stage in stages:
        order += 1
        db.session.add(
            LearningTask(
                roadmap_id=roadmap.id,
                skill_id=None,
                title=stage,
                description=f"Curriculum stage for {role.name}: {stage}",
                status="not_started",
                order_index=order,
                estimated_hours=8.0,
            )
        )

    for gap in analysis["gaps"]:
        order += 1
        task = LearningTask(
            roadmap_id=roadmap.id,
            skill_id=gap["skill_id"],
            title=_task_title(
                gap["skill_name"], gap["current_level"], gap["required_level"]
            ),
            description=(
                f"Status: {gap['status']}. Need level {gap['required_level']}, "
                f"currently {gap['current_level']} (gap {gap['gap_level']})."
            ),
            status="not_started",
            order_index=order,
            estimated_hours=_estimated_hours(gap["gap_level"], gap["importance"]),
        )
        db.session.add(task)

    if order == 0:
        db.session.add(
            LearningTask(
                roadmap_id=roadmap.id,
                skill_id=None,
                title=f"Maintain readiness for {role.name}",
                description="All required skills currently meet or exceed targets.",
                status="not_started",
                order_index=1,
                estimated_hours=4.0,
            )
        )

    update_roadmap_progress(roadmap)
    db.session.commit()
    return roadmap


def update_roadmap_progress(roadmap: LearningRoadmap) -> float:
    """Recompute progress_pct from task statuses. Returns new percentage."""
    tasks = list(roadmap.tasks or [])
    if not tasks:
        # Reload from DB if relationship not populated.
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


def set_task_status(task_id: int, status: str) -> LearningTask:
    if status not in TASK_STATUSES:
        raise ValueError(
            f"Invalid status {status!r}. Expected one of {TASK_STATUSES}."
        )
    task = db.session.get(LearningTask, task_id)
    if task is None:
        raise ValueError(f"LearningTask id={task_id} not found.")
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
    for t in tasks:
        by_status[t.status] = by_status.get(t.status, 0) + 1
    return {
        "roadmap_id": roadmap.id,
        "title": roadmap.title,
        "role_id": roadmap.role_id,
        "progress_pct": roadmap.progress_pct,
        "task_counts": by_status,
        "tasks": [
            {
                "id": t.id,
                "title": t.title,
                "skill_id": t.skill_id,
                "status": t.status,
                "order_index": t.order_index,
                "estimated_hours": t.estimated_hours,
            }
            for t in tasks
        ],
    }
