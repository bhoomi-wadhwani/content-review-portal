from sqlalchemy import case, func
from flask import Blueprint, abort, redirect, render_template, request, url_for

from models import Client, Submission, db

clients_bp = Blueprint("clients", __name__)


def _client_stats():
    rows = (
        db.session.query(
            Client,
            func.count(Submission.id).label("total"),
            func.sum(case((Submission.status == "pending", 1), else_=0)).label("n_pending"),
            func.sum(case((Submission.status == "approved", 1), else_=0)).label("n_approved"),
            func.sum(case((Submission.status == "rejected", 1), else_=0)).label("n_rejected"),
            func.sum(case((Submission.status == "changes_requested", 1), else_=0)).label("n_changes"),
        )
        .outerjoin(Submission)
        .group_by(Client.id)
        .order_by(Client.name)
        .all()
    )
    return [
        {
            "client":     row.Client,
            "total":      row.total or 0,
            "n_pending":  (row.n_pending or 0) + (row.n_changes or 0),
            "n_approved": row.n_approved or 0,
            "n_rejected": row.n_rejected or 0,
        }
        for row in rows
    ]


@clients_bp.route("/clients", methods=["GET"])
def list_clients():
    return render_template("clients.html", stats=_client_stats())


@clients_bp.route("/clients", methods=["POST"])
def add_client():
    name  = request.form.get("name", "").strip()
    email = request.form.get("email", "").strip()

    if not name or not email:
        return render_template(
            "clients.html", stats=_client_stats(),
            error="Name and email are required."
        ), 400

    if Client.query.filter_by(email=email).first():
        return render_template(
            "clients.html", stats=_client_stats(),
            error=f"A client with email '{email}' already exists."
        ), 400

    db.session.add(Client(name=name, email=email))
    db.session.commit()
    return redirect(url_for("clients.list_clients"))


@clients_bp.route("/clients/<int:client_id>")
def client_detail(client_id):
    client = db.session.get(Client, client_id)
    if client is None:
        abort(404)
    submissions = (
        Submission.query
        .filter_by(client_id=client_id)
        .order_by(Submission.created_at.desc())
        .all()
    )
    return render_template("client_detail.html", client=client, submissions=submissions)


@clients_bp.route("/clients/<int:client_id>/delete", methods=["POST"])
def delete_client(client_id):
    client = db.session.get(Client, client_id)
    if client is None:
        abort(404)

    if client.submissions.count() > 0:
        return render_template(
            "clients.html", stats=_client_stats(),
            error=f"Cannot delete '{client.name}' — they have submissions. Delete those first."
        ), 400

    db.session.delete(client)
    db.session.commit()
    return redirect(url_for("clients.list_clients"))
