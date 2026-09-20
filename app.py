import os
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, send_from_directory

load_dotenv()

from extensions import mail
from models import db
from routes.clients import clients_bp
from routes.dashboard import dashboard_bp
from routes.upload import upload_bp
from routes.review import review_bp

BASE_DIR = Path(__file__).parent


def _timeago(dt: datetime) -> str:
    now = datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    secs = int((now - dt).total_seconds())
    if secs < 60:
        return "just now"
    if secs < 3600:
        m = secs // 60
        return f"{m}m ago"
    if secs < 86400:
        h = secs // 3600
        return f"{h}h ago"
    d = secs // 86400
    return f"{d}d ago"


def create_app():
    app = Flask(__name__)
    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "change-me-in-production")
    db_path = os.environ.get("DB_PATH", str(BASE_DIR / "submissions.db"))
    app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{db_path}"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["UPLOAD_FOLDER"] = os.environ.get("UPLOAD_FOLDER", str(BASE_DIR / "static" / "uploads"))
    app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024  # 50 MB limit

    # Flask-Mail — credentials sourced from env vars, never hardcoded.
    app.config["MAIL_SERVER"] = "smtp.gmail.com"
    app.config["MAIL_PORT"] = 587
    app.config["MAIL_USE_TLS"] = True
    app.config["MAIL_USERNAME"] = os.environ.get("GMAIL_ADDRESS")
    app.config["MAIL_PASSWORD"] = os.environ.get("GMAIL_APP_PASSWORD")
    app.config["MAIL_DEFAULT_SENDER"] = os.environ.get("GMAIL_ADDRESS")

    db.init_app(app)
    mail.init_app(app)

    import json as _json
    app.jinja_env.filters["timeago"]  = _timeago
    app.jinja_env.filters["fromjson"] = _json.loads

    @app.route("/files/<path:filename>")
    def serve_upload(filename):
        return send_from_directory(app.config["UPLOAD_FOLDER"], filename)

    app.register_blueprint(upload_bp)
    app.register_blueprint(review_bp)
    app.register_blueprint(clients_bp)
    app.register_blueprint(dashboard_bp)

    with app.app_context():
        db.create_all()
        _migrate(db)

    return app


def _migrate(db):
    """Add any missing columns that db.create_all() won't backfill."""
    with db.engine.connect() as conn:
        existing = {
            row[1]
            for row in conn.execute(db.text("PRAGMA table_info(submissions)"))
        }
    needed = {
        "watermarked_path": "ALTER TABLE submissions ADD COLUMN watermarked_path VARCHAR(500)",
        "client_id":        "ALTER TABLE submissions ADD COLUMN client_id INTEGER",
        "team_note":        "ALTER TABLE submissions ADD COLUMN team_note TEXT",
        "social_targets":   "ALTER TABLE submissions ADD COLUMN social_targets TEXT",
        "social_caption":   "ALTER TABLE submissions ADD COLUMN social_caption TEXT",
        "social_posted":    "ALTER TABLE submissions ADD COLUMN social_posted TEXT",
    }
    with db.engine.begin() as conn:
        for col, ddl in needed.items():
            if col not in existing:
                conn.execute(db.text(ddl))
        # Strip legacy 'uploads/' prefix so paths are relative to UPLOAD_FOLDER
        conn.execute(db.text(
            "UPDATE submissions SET watermarked_path = SUBSTR(watermarked_path, 9) "
            "WHERE watermarked_path LIKE 'uploads/%'"
        ))


app = create_app()

if __name__ == "__main__":
    app.run(debug=True)
