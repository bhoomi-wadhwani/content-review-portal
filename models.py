from datetime import datetime, timezone
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


class Client(db.Model):
    __tablename__ = "clients"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    email = db.Column(db.String(254), unique=True, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    submissions = db.relationship("Submission", back_populates="client", lazy="dynamic")

    def __repr__(self):
        return f"<Client {self.id} {self.name!r}>"


class Submission(db.Model):
    __tablename__ = "submissions"

    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(255), nullable=False)
    file_type = db.Column(db.String(100), nullable=False)
    status = db.Column(
        db.Enum("pending", "approved", "rejected", "changes_requested", name="status_enum"),
        nullable=False,
        default="pending",
    )
    client_comment = db.Column(db.Text, nullable=True)
    review_token = db.Column(db.String(36), unique=True, nullable=False, index=True)
    watermarked_path = db.Column(db.String(500), nullable=True)
    team_note = db.Column(db.Text, nullable=True)
    social_targets = db.Column(db.Text, nullable=True)   # comma-separated: "twitter,instagram"
    social_caption = db.Column(db.Text, nullable=True)
    social_posted  = db.Column(db.Text, nullable=True)   # JSON result per platform
    client_id = db.Column(db.Integer, db.ForeignKey("clients.id"), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    client = db.relationship("Client", back_populates="submissions")
    video_comments = db.relationship("VideoComment", back_populates="submission")

    def __repr__(self):
        return f"<Submission {self.id} {self.filename!r} [{self.status}]>"


class VideoComment(db.Model):
    __tablename__ = "video_comments"

    id = db.Column(db.Integer, primary_key=True)
    submission_id = db.Column(db.Integer, db.ForeignKey("submissions.id"), nullable=False, index=True)
    timestamp_seconds = db.Column(db.Float, nullable=False)
    comment_text = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    submission = db.relationship("Submission", back_populates="video_comments")

    @property
    def timestamp_str(self):
        m = int(self.timestamp_seconds // 60)
        s = int(self.timestamp_seconds % 60)
        return f"{m}:{s:02d}"
