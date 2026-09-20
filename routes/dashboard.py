from flask import Blueprint, render_template

from models import Client, Submission

dashboard_bp = Blueprint("dashboard", __name__)


def parse_feedback(vc):
    return {
        "timestamp": vc.timestamp_str,
        "text": vc.comment_text,
        "seconds": vc.timestamp_seconds,
    }


@dashboard_bp.route("/dashboard")
def dashboard():
    submissions = (
        Submission.query
        .outerjoin(Client)
        .order_by(Submission.created_at.desc())
        .all()
    )

    return render_template(
        "dashboard.html",
        pending=[s for s in submissions if s.status == "pending"],
        changes=[s for s in submissions if s.status == "changes_requested"],
        approved=[s for s in submissions if s.status == "approved"],
        rejected=[s for s in submissions if s.status == "rejected"],
        parse_feedback=parse_feedback,
    )
