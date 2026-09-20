import mimetypes
import uuid
from pathlib import Path

from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for
from flask_mail import Message

from extensions import mail
from models import Client, Submission, db
from services.watermark import apply_watermark

upload_bp = Blueprint("upload", __name__)

_WATERMARKABLE = {"image/", "video/", "application/pdf"}

# Magic-byte signatures for types browsers commonly misreport.
_MAGIC = [
    (b"%PDF",               "application/pdf"),
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"\xff\xd8\xff",      "image/jpeg"),
    (b"GIF87a",            "image/gif"),
    (b"GIF89a",            "image/gif"),
    (b"RIFF",              None),  # may be WebP or WAV — fall through
]

# Extensions browsers commonly misreport that magic bytes won't catch.
_EXT_OVERRIDES = {
    ".heic": "image/heic",
    ".heif": "image/heif",
    ".webp": "image/webp",
    ".avif": "image/avif",
}


def _detect_mime(saved_path: Path, browser_type: str) -> str:
    """Return a reliable MIME type by reading magic bytes then falling back to extension."""
    ext = saved_path.suffix.lower()
    if ext in _EXT_OVERRIDES:
        return _EXT_OVERRIDES[ext]
    try:
        with open(saved_path, "rb") as f:
            header = f.read(8)
        for sig, mime in _MAGIC:
            if header[: len(sig)] == sig and mime:
                return mime
    except OSError:
        pass
    guessed, _ = mimetypes.guess_type(saved_path.name)
    return guessed or browser_type or "application/octet-stream"


@upload_bp.route("/", methods=["GET"])
def index():
    clients = Client.query.order_by(Client.name).all()
    return render_template("upload.html", clients=clients)


@upload_bp.route("/upload", methods=["POST"])
def upload_file():
    clients = Client.query.order_by(Client.name).all()

    file = request.files.get("file")
    if not file or file.filename == "":
        return render_template("upload.html", clients=clients, error="No file selected."), 400

    client_id = request.form.get("client_id", type=int)
    client = db.session.get(Client, client_id) if client_id else None
    if not client:
        return render_template("upload.html", clients=clients, error="Please select a valid client."), 400

    token = str(uuid.uuid4())
    safe_filename = f"{token}_{Path(file.filename).name}"
    upload_dir = Path(current_app.config["UPLOAD_FOLDER"])
    saved_path = upload_dir / safe_filename
    file.save(saved_path)

    file_type = _detect_mime(saved_path, file.content_type)

    watermarked_rel = None
    if any(file_type.startswith(p) for p in _WATERMARKABLE):
        try:
            wm_abs = apply_watermark(str(saved_path), file_type)
            upload_dir = Path(current_app.config["UPLOAD_FOLDER"])
            watermarked_rel = Path(wm_abs).relative_to(upload_dir).as_posix()
        except Exception as exc:
            current_app.logger.warning("Watermark failed for %s: %s", saved_path.name, exc)

    team_note      = request.form.get("team_note", "").strip() or None
    social_targets = ",".join(request.form.getlist("social_targets")) or None
    social_caption = request.form.get("social_caption", "").strip() or None

    submission = Submission(
        filename=file.filename,
        file_type=file_type,
        review_token=token,
        watermarked_path=watermarked_rel,
        team_note=team_note,
        social_targets=social_targets,
        social_caption=social_caption,
        client_id=client.id,
    )
    db.session.add(submission)
    db.session.commit()

    review_url = url_for("review.review_page", token=token, _external=True)

    try:
        _send_review_email(client, review_url, team_note)
        flash(
            f"Content watermarked and review link sent to {client.name} ({client.email}).",
            "success",
        )
    except Exception as exc:
        flash(
            f"File uploaded, but email to {client.email} failed: {exc}. "
            "Copy the review link below to share manually.",
            "warning",
        )

    return redirect(url_for("upload.success", token=token))


@upload_bp.route("/upload/success")
def success():
    token = request.args.get("token", "")
    submission = Submission.query.filter_by(review_token=token).first_or_404()
    review_url = url_for("review.review_page", token=token, _external=True)
    return render_template("upload_success.html", submission=submission, review_url=review_url)


def _send_review_email(client: Client, review_url: str, team_note: str | None = None) -> None:
    note_block = f"\n\nMessage from the team:\n    {team_note}" if team_note else ""
    msg = Message(
        subject="Content Ready for Review",
        recipients=[client.email],
        body=(
            f"Hi {client.name},\n\n"
            "Your content is ready for your review. Use the private link below to view "
            f"the watermarked preview and leave your decision:{note_block}\n\n"
            f"    {review_url}\n\n"
            "No login required — this link is unique to your submission.\n\n"
            "Best regards,\nThe Review Team"
        ),
    )
    mail.send(msg)
