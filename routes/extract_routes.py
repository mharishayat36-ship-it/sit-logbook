"""Word -> JSON extraction, the editable preview, exports, draft editing and the round-trip check."""
import os
from datetime import date

from flask import (Blueprint, Response, current_app, flash, jsonify, redirect, render_template,
                   request, send_file, url_for)
from werkzeug.utils import secure_filename

from models import UploadedDocument, db_session
from routes.documents import MODES
from routes.helpers import (active_document, analysis_for, create_draft, document_path,
                            get_document, get_draft, get_schedule, list_mappings, log_history,
                            prune_old_drafts, timestamp, upsert_entries)
from services import exporter
from services.common import FIELDS, FIELD_LABELS, long_date
from services.document_extractor import extract_records
from services.field_mapper import build_targets
from services.json_validator import validate_item
from services.round_trip_validator import run_round_trip

bp = Blueprint("extract", __name__)
drafts_bp = Blueprint("drafts", __name__)


# ---------------------------------------------------------------- exports
def send_export(records, fmt, basename):
    """Write the export into /exports (kept for your records) and send it to the browser."""
    fmt = fmt.lower()
    if fmt not in ("json", "csv", "xlsx"):
        flash("Unknown export format.", "error")
        return redirect(url_for("main.index"))
    name = f"{secure_filename(basename) or 'logbook'}_{timestamp()}.{fmt}"
    path = os.path.join(current_app.config["EXPORT_FOLDER"], name)
    if fmt == "json":
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(exporter.to_json(records))
        mime = "application/json"
    elif fmt == "csv":
        with open(path, "w", encoding="utf-8-sig", newline="") as fh:  # BOM so Excel reads UTF-8
            fh.write(exporter.to_csv(records))
        mime = "text/csv"
    else:
        with open(path, "wb") as fh:
            fh.write(exporter.to_xlsx_bytes(records))
        mime = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    return send_file(path, mimetype=mime, as_attachment=True, download_name=name)


# ---------------------------------------------------------------- extract page
@bp.route("/extract")
def extract_page():
    docs = db_session.query(UploadedDocument).order_by(UploadedDocument.id.desc()).all()
    doc = get_document(request.args.get("doc", type=int)) or active_document()
    analysis, error = analysis_for(doc)
    targets = []
    if analysis:
        found, _ = build_targets(analysis["tables"], list_mappings(db_session), include_auto=True)
        for t in found:
            targets.append({"name": t["name"], "source": t["source"],
                            "tables": [analysis["tables"][i]["name"] for i in t["table_indexes"]],
                            "fields": sorted({f for c in t["columns"].values() for f in c},
                                             key=FIELDS.index)})
    return render_template("extract.html", docs=docs, doc=doc, analysis=analysis, error=error,
                           targets=targets, labels=FIELD_LABELS)


@bp.route("/extract/run", methods=["POST"])
def run_extract():
    doc = get_document(request.form.get("doc_id", type=int))
    if doc is None:
        flash("Choose or upload a Word document first.", "error")
        return redirect(url_for("extract.extract_page"))
    schedule = get_schedule()
    try:
        result = extract_records(document_path(doc), list_mappings(db_session), schedule.start.year,
                                 skip_empty=request.form.get("skip_empty") == "1")
    except Exception as exc:
        log_history(doc.original_name, "extract", 0, f"Failed: {exc}")
        flash(f"The document could not be read: {exc}", "error")
        return redirect(url_for("extract.extract_page"))
    records = result["records"]
    if not records:
        log_history(doc.original_name, "extract", 0, "No records found", [], {"messages": result["messages"][:20]})
        for m in result["messages"]:
            flash(m["text"], "error" if m["level"] == "error" else "warning")
        flash("No records were found. Check the field mapping or whether the logbook has any data yet.", "error")
        return redirect(url_for("extract.extract_page", doc=doc.id))
    draft = create_draft("extract", records, {"doc_id": doc.id, "filename": doc.original_name,
                                              "messages": result["messages"], "stats": result["stats"],
                                              "tables_used": result["tables_used"]})
    prune_old_drafts()
    log_history(doc.original_name, "extract", len(records), "Successful", records,
                {"stats": result["stats"], "warnings": len(result["messages"])})
    return redirect(url_for("extract.preview", draft_id=draft.id))


def row_statuses(records, schedule):
    """Per-record status for the preview (re-validated each time so edits are reflected)."""
    seen, out = set(), []
    for rec in records:
        res = validate_item({"scope": None, "raw": rec}, schedule, seen, schedule.start.year)
        out.append({"label": res["label"], "status": res["status"], "messages": res["messages"]})
    return out


@bp.route("/extract/preview/<int:draft_id>")
def preview(draft_id):
    draft = get_draft(draft_id)
    if draft is None or draft.kind != "extract":
        flash("That extraction no longer exists. Extract the document again.", "error")
        return redirect(url_for("extract.extract_page"))
    records = draft.records
    meta = draft.meta
    statuses = row_statuses(records, get_schedule())
    return render_template("extraction_preview.html", draft=draft, records=records, meta=meta,
                           statuses=statuses, warnings=meta.get("messages", []), modes=MODES,
                           labels=FIELD_LABELS, doc=active_document())


@bp.route("/extract/<int:draft_id>/export/<fmt>")
def export(draft_id, fmt):
    draft = get_draft(draft_id)
    if draft is None:
        flash("That working set no longer exists.", "error")
        return redirect(url_for("extract.extract_page"))
    base = os.path.splitext(draft.meta.get("filename", "logbook"))[0] + "_extracted"
    return send_export(draft.records, fmt, base)


# ---------------------------------------------------------------- shared draft editing
@drafts_bp.route("/draft/<int:draft_id>/save", methods=["POST"])
def save_draft(draft_id):
    """Receive the edited table as JSON, validate every row, store it only if there are no errors."""
    draft = get_draft(draft_id)
    payload = request.get_json(silent=True)
    if draft is None or not isinstance(payload, dict) or not isinstance(payload.get("records"), list):
        return jsonify({"ok": False, "error": "Invalid request."}), 400
    if len(payload["records"]) > 2000:
        return jsonify({"ok": False, "error": "Too many records."}), 400
    schedule = get_schedule()
    seen, rows, clean, has_error = set(), [], [], False
    for raw in payload["records"]:
        if not isinstance(raw, dict):
            raw = {}
        raw = {k: v for k, v in raw.items() if k in FIELDS}
        res = validate_item({"scope": None, "raw": raw}, schedule, seen, schedule.start.year)
        if res["day_mismatch"]:
            res["record"]["day"] = res["day_calc"]
            res["messages"].append({"level": "info", "text": f"Day corrected to {res['day_calc']}."})
        rows.append({"status": res["status"], "label": res["label"], "messages": res["messages"],
                     "record": res["record"]})
        has_error = has_error or res["status"] == "error"
        if res["record"] and res["status"] != "error":
            clean.append(res["record"])
    if has_error:
        return jsonify({"ok": False, "error": "Fix the highlighted rows before saving.", "rows": rows}), 400
    clean.sort(key=lambda r: r["date"])
    draft.records = clean
    db_session.commit()
    return jsonify({"ok": True, "count": len(clean), "rows": rows})


@drafts_bp.route("/draft/<int:draft_id>/to-database", methods=["POST"])
def to_database(draft_id):
    draft = get_draft(draft_id)
    if draft is None:
        flash("That working set no longer exists.", "error")
        return redirect(url_for("main.index"))
    created, updated = upsert_entries(draft.records, get_schedule())
    flash(f"Saved to database: {created} new and {updated} updated daily entries.", "success")
    target = {"extract": "extract.preview", "weekly": "main.weekly_preview"}.get(draft.kind)
    return redirect(url_for(target, draft_id=draft.id) if target else url_for("main.entries"))


# ---------------------------------------------------------------- round trip
@bp.route("/roundtrip/<int:draft_id>")
def round_trip(draft_id):
    from routes.helpers import resolve_draft
    draft = get_draft(draft_id)
    doc = get_document(request.args.get("doc_id", type=int)) or active_document()
    if draft is None or doc is None:
        flash("A working set and a Word template are both needed for the round-trip check.", "error")
        return redirect(url_for("main.index"))
    flat, tables, _ = resolve_draft(draft, request.args.get("day_policy", "correct"), doc)
    report = run_round_trip(document_path(doc), flat, tables, list_mappings(db_session),
                            get_schedule().start.year)
    log_history(doc.original_name, "round-trip", report["records"],
                "Passed" if report["ok"] else "Differences found", flat + [r for rs in tables.values() for r in rs],
                {"warnings": report["warnings"]})
    return render_template("roundtrip.html", report=report, draft=draft, doc=doc)
