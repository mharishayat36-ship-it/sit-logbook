"""JSON import: paste -> validate -> preview -> (Word | database)."""
from flask import Blueprint, flash, redirect, render_template, request, url_for

from models import JsonImport, db_session
from routes.documents import MODES
from routes.helpers import (active_document, create_draft, get_draft, get_schedule, log_json_import,
                            prune_old_drafts, resolve_draft, upsert_entries, validate_json_text)
from services.common import FIELDS, FIELD_LABELS

bp = Blueprint("json_routes", __name__)


@bp.route("/json/import", methods=["GET", "POST"])
def import_page():
    doc = active_document()
    if request.method == "POST":
        text = request.form.get("json_text", "")
        parsed, validation = validate_json_text(text, doc)
        if validation is None:
            flash(parsed["error"], "error")
            return render_template("json_import.html", text=text, error=parsed["error"], doc=doc)
        draft = create_draft("json", source_text=text)
        prune_old_drafts()
        return redirect(url_for("json_routes.preview", draft_id=draft.id))

    text = ""
    draft = get_draft(request.args.get("draft", type=int)) if request.args.get("draft") else None
    if draft is not None and draft.kind == "json":
        text = draft.source_text
    elif request.args.get("import_id"):
        row = db_session.get(JsonImport, request.args.get("import_id", type=int))
        text = row.source_data if row else ""
    return render_template("json_import.html", text=text, error=None, doc=doc)


@bp.route("/json/preview/<int:draft_id>")
def preview(draft_id):
    draft = get_draft(draft_id)
    if draft is None or draft.kind != "json":
        flash("That import no longer exists. Paste the JSON again.", "error")
        return redirect(url_for("json_routes.import_page"))
    doc = active_document()
    parsed, validation = validate_json_text(draft.source_text, doc)
    if validation is None:
        flash(parsed["error"], "error")
        return redirect(url_for("json_routes.import_page", draft=draft.id))
    # Group the usable records for the preview tables (flat records and one group per table).
    groups = {}
    for r in validation["results"]:
        if r["record"]:
            groups.setdefault(r["scope"], []).append(r)
    preview_groups = []
    for scope, items in groups.items():
        used = [f for f in FIELDS if f != "date" and any(i["record"].get(f) for i in items)]
        preview_groups.append({"name": scope, "fields": ["date"] + used, "rows": items})
    return render_template("json_preview.html", draft=draft, validation=validation, doc=doc,
                           groups=preview_groups, modes=MODES, labels=FIELD_LABELS)


@bp.route("/json/<int:draft_id>/save-db", methods=["POST"])
def save_to_database(draft_id):
    draft = get_draft(draft_id)
    if draft is None:
        flash("That import no longer exists.", "error")
        return redirect(url_for("json_routes.import_page"))
    policy = request.form.get("day_policy", "correct")
    if policy == "cancel":
        flash("Import cancelled.", "info")
        return redirect(url_for("json_routes.import_page"))
    flat, tables, validation = resolve_draft(draft, policy, active_document())
    records = flat + [r for rs in tables.values() for r in rs]
    if not records:
        flash("There are no valid records to save.", "error")
        return redirect(url_for("json_routes.preview", draft_id=draft.id))
    created, updated = upsert_entries(records, get_schedule())
    row = log_json_import(records, "Saved to database", draft.source_text)
    return render_template("success.html", title="Saved to database",
                           message=f"Import #{row.id}: {created} new and {updated} updated daily entries "
                                   f"were saved to the database.",
                           download=None, stats=None, warnings=[], roundtrip=None, extract=None)


@bp.route("/json/<int:draft_id>/cancel", methods=["POST"])
def cancel(draft_id):
    draft = get_draft(draft_id)
    if draft is not None:
        db_session.delete(draft)
        db_session.commit()
    flash("Import cancelled. Nothing was changed.", "info")
    return redirect(url_for("json_routes.import_page"))
