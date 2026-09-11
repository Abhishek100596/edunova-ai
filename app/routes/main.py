"""Public landing and about pages."""

from flask import Blueprint, render_template

bp = Blueprint("main", __name__)


def _render_landing():
    return render_template("main/landing.html")


bp.add_url_rule("/", endpoint="index", view_func=_render_landing)
bp.add_url_rule("/landing", endpoint="landing", view_func=_render_landing)


@bp.route("/about")
def about():
    return render_template(
        "about.html",
        features=[
            "Placement prediction & explainability",
            "Skill-gap analysis vs career roles",
            "Personalized learning roadmaps",
            "Resume analysis & JD matching",
            "Mock interviews with scored feedback",
            "AI coach grounded in your real profile",
        ],
    )
