"""Internship Training Logbook Automation System - Flask application entry point.

Run with:   python app.py      then open  http://127.0.0.1:5000
"""
import os
from datetime import date, datetime

from flask import Flask, flash, redirect, render_template, request, url_for

from config import Config
from models import db_session, init_db
from services.common import FIELD_LABELS, FIELDS, MONTH_ABBR
from services.field_mapper import seed_default_mappings


def create_app(overrides=None) -> Flask:
    app = Flask(__name__)
    app.config.from_object(Config)
    if overrides:
        app.config.update(overrides)

    for key in ("UPLOAD_FOLDER", "GENERATED_FOLDER", "EXPORT_FOLDER"):
        os.makedirs(app.config[key], exist_ok=True)

    init_db(app.config["DATABASE_URI"])
    with app.app_context():
        from routes.helpers import get_internship
        get_internship()  # creates the internship row on first run
        seed_default_mappings(db_session)

    from routes.documents import bp as documents_bp
    from routes.extract_routes import bp as extract_bp, drafts_bp
    from routes.json_routes import bp as json_bp
    from routes.main import bp as main_bp
    for bp in (main_bp, documents_bp, json_bp, extract_bp, drafts_bp):
        app.register_blueprint(bp)

    @app.teardown_appcontext
    def shutdown_session(exception=None):
        db_session.remove()

    @app.context_processor
    def inject_globals():
        from routes.helpers import active_document
        return {"FIELDS": FIELDS, "FIELD_LABELS": FIELD_LABELS, "active_doc": active_document(),
                "app_title": app.config["INTERNSHIP_TITLE"]}

    @app.template_filter("pretty_date")
    def pretty_date(value):
        """'2026-09-28' -> '28 Sep 2026'."""
        try:
            d = value if isinstance(value, date) else date.fromisoformat(str(value))
            return f"{d.day:02d} {MONTH_ABBR[d.month - 1]} {d.year}"
        except ValueError:
            return str(value or "")

    @app.template_filter("pretty_dt")
    def pretty_dt(value):
        if not isinstance(value, datetime):
            return ""
        return f"{value.day:02d} {MONTH_ABBR[value.month - 1]} {value.year}, {value:%H:%M}"

    @app.template_filter("filesize")
    def filesize(n):
        n = n or 0
        return f"{n / 1024:.0f} KB" if n < 1024 * 1024 else f"{n / 1024 / 1024:.1f} MB"

    # ---- error handling: never a blank page or a stack trace
    @app.errorhandler(413)
    def too_large(_):
        flash("That file is too large. The limit is 16 MB.", "error")
        return redirect(request.referrer or url_for("main.index"))

    @app.errorhandler(404)
    def not_found(_):
        return render_template("error.html", code=404, message="That page does not exist."), 404

    @app.errorhandler(500)
    def server_error(_):
        db_session.rollback()
        return render_template("error.html", code=500,
                               message="Something went wrong. Nothing was lost; please go back and try again."), 500

    return app


if __name__ == "__main__":
    create_app().run(host="127.0.0.1", port=5000, debug=os.environ.get("LOGBOOK_DEBUG") == "1")
