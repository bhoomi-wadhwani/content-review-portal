from pathlib import Path

from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, url_for
from flask_mail import Message

from extensions import mail
from models import Submission, VideoComment, db

review_bp = Blueprint("review", __name__)

_ALLOWED_STATUSES = {"approved", "rejected", "changes_requested"}

_SUBJECTS = {
    "approved":          "{name} approved: {filename}",
    "rejected":          "{name} rejected: {filename}",
    "changes_requested": "{name} requested changes: {filename}",
}

_BODIES = {
    "approved": (
        "Hi,\n\n"
        "{name} has approved \"{filename}\".\n\n"
        "View the submission here:\n    {url}\n\n"
        "Best,\nReview Portal"
    ),
    "rejected": (
        "Hi,\n\n"
        "{name} has rejected \"{filename}\".{comment_block}\n\n"
        "View the submission here:\n    {url}\n\n"
        "Best,\nReview Portal"
    ),
    "changes_requested": (
        "Hi,\n\n"
        "{name} has requested changes on \"{filename}\".{comment_block}\n\n"
        "View the submission here:\n    {url}\n\n"
        "Best,\nReview Portal"
    ),
}


def _send_decision_email(submission: Submission, review_url: str) -> None:
    if not submission.client:
        return
    comment_block = (
        f"\n\nFeedback:\n    {submission.client_comment}"
        if submission.client_comment
        else ""
    )
    body = _BODIES[submission.status].format(
        name=submission.client.name,
        filename=submission.filename,
        url=review_url,
        comment_block=comment_block,
    )
    team_email = current_app.config.get("MAIL_DEFAULT_SENDER")
    if not team_email:
        return
    msg = Message(
        subject=_SUBJECTS[submission.status].format(
            name=submission.client.name, filename=submission.filename
        ),
        recipients=[team_email],
        body=body,
    )
    mail.send(msg)


@review_bp.route("/review/<token>/internal")
def review_internal(token):
    submission = Submission.query.filter_by(review_token=token).first()
    if submission is None:
        abort(404)
    review_url = url_for("review.review_page", token=token, _external=True)
    return render_template("review_internal.html", submission=submission, review_url=review_url)


@review_bp.route("/review/<token>")
def review_page(token):
    submission = Submission.query.filter_by(review_token=token).first()
    if submission is None:
        abort(404)
    return render_template("review.html", submission=submission)


@review_bp.route("/review/<token>/decide", methods=["POST"])
def decide(token):
    submission = Submission.query.filter_by(review_token=token).first()
    if submission is None:
        abort(404)

    new_status = request.form.get("status")
    if new_status not in _ALLOWED_STATUSES:
        abort(400)

    submission.status = new_status
    comment = request.form.get("comment", "").strip()
    if comment:
        submission.client_comment = comment

    ts_seconds = request.form.getlist("ts_seconds[]")
    ts_texts   = request.form.getlist("ts_texts[]")
    for sec_str, txt in zip(ts_seconds, ts_texts):
        txt = txt.strip()
        if not txt:
            continue
        try:
            sec = float(sec_str)
        except (ValueError, TypeError):
            continue
        db.session.add(VideoComment(
            submission_id=submission.id,
            timestamp_seconds=sec,
            comment_text=txt,
        ))

    db.session.commit()

    if new_status == "approved":
        try:
            from services.social import post_on_approval
            post_on_approval(submission)
            db.session.commit()
        except Exception:
            pass

    review_url = url_for("review.review_page", token=token, _external=True)
    try:
        _send_decision_email(submission, review_url)
    except Exception:
        pass  # don't block the redirect if mail is misconfigured

    return redirect(url_for("review.review_page", token=token))


@review_bp.route("/submission/<token>/delete", methods=["POST"])
def delete_submission(token):
    submission = Submission.query.filter_by(review_token=token).first()
    if submission is None:
        abort(404)

    upload_dir = Path(current_app.config["UPLOAD_FOLDER"])
    orig = upload_dir / f"{token}_{Path(submission.filename).name}"
    if orig.exists():
        orig.unlink()

    if submission.watermarked_path:
        wm = Path(current_app.root_path) / "static" / submission.watermarked_path
        if wm.exists():
            wm.unlink()

    for vc in list(submission.video_comments):
        db.session.delete(vc)
    db.session.delete(submission)
    db.session.commit()

    flash("Submission deleted.", "success")
    return redirect(url_for("dashboard.dashboard"))
