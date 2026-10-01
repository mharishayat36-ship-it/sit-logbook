"""Word documents: upload, analyzer, field mappings, generation (preview -> confirm) and downloads."""
import os
import uuid
import zipfile
from datetime import date

from docx import Document
from flask import (Blueprint, abort, current_app, flash, redirect, render_template, request,
                   send_from_directory, url_for)
from werkzeug.utils import secure_filename

from models import FieldMapping, UploadedDocument, db_session
from routes.helpers import (active_document, analysis_for, document_path, entries_as_records,
                            create_draft, get_document, get_draft, get_schedule, log_history,
                            log_json_import, resolve_draft, timestamp, upsert_entries)
from services.common import FIELDS, FIELD_LABELS
from services.field_mapper import (DEFAULT_MAPPINGS, auto_detect_mappings, list_mappings,
                                   mappings_match_document, replace_all_mappings)
from services.word_generator import MODES, apply_plan, build_plan, plan_has_work

bp = Blueprint("documents", __name__)

# where the upload form may send the user afterwards
NEXT_PAGES = {"analyzer": "documents.analyzer", "extract": "extract.extract_page",
              "json": "json_routes.import_page", "generate": "documents.generate_page"}


# ---------------------------------------------------------------- upload
def _valid_docx(path) -> str:
    """Return '' if the file is a real .docx, otherwise a reason."""
    if not zipfile.is_zipfile(path):
        return "The file is not a valid .docx document."
    try:
        with zipfile.ZipFile(path) as zf:
            names = zf.namelist()
            if "word/document.xml" not in names:
                return "The file does not look like a Word document."
            if sum(i.file_size for i in zf.infolist()) > 300 * 1024 * 1024:
                return "The document expands to an unreasonable size and was rejected."
        Document(path)
    except Exception:
        return "The Word document is damaged or unreadable."
    return ""


@bp.route("/documents/upload", methods=["POST"])
def upload():
    next_endpoint = NEXT_PAGES.get(request.form.get("next", ""), "documents.analyzer")
    file = request.files.get("document")
    if file is None or not file.filename:
        flash("Please choose a .docx file to upload.", "error")
        return redirect(url_for(next_endpoint))
    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if ext not in current_app.config["ALLOWED_EXTENSIONS"]:
        flash("Only .docx files are accepted.", "error")
        return redirect(url_for(next_endpoint))

    safe = secure_filename(file.filename) or "logbook.docx"
    if not safe.lower().endswith(".docx"):
        safe += ".docx"
    stored = f"{uuid.uuid4().hex[:12]}_{safe}"
    path = os.path.join(current_app.config["UPLOAD_FOLDER"], stored)
    file.save(path)
    problem = _valid_docx(path)
    if problem:
        os.remove(path)
        flash(problem, "error")
        return redirect(url_for(next_endpoint))

    db_session.query(UploadedDocument).update({"is_active": False})
    doc = UploadedDocument(original_name=file.filename.replace("\\", "/").split("/")[-1][:250],
                           stored_name=stored, size=os.path.getsize(path), is_active=True)
    db_session.add(doc)
    db_session.commit()
    flash(f"Uploaded '{doc.original_name}' and selected it as the active template.", "success")

    # Make the app usable immediately: if no saved mapping fits this document, detect one.
    analysis, error = analysis_for(doc)
    if analysis:
        mappings = list_mappings(db_session)
        if not mappings_match_document(mappings, analysis["tables"]):
            detected = auto_detect_mappings(analysis["tables"])
            if detected:
                known = {(m["json_field"], m["word_table"].lower(), m["word_column"].lower()) for m in mappings}
                for m in detected:
                    if (m["json_field"], m["word_table"].lower(), m["word_column"].lower()) not in known:
                        db_session.add(FieldMapping(**m))
                db_session.commit()
                flash("Field mappings were detected automatically from this document's column "
                      "headers. Review them on the Field Mapping page.", "info")
    elif error:
        flash(error, "error")
    return redirect(url_for(next_endpoint))


@bp.route("/documents/<int:doc_id>/activate", methods=["POST"])
def activate(doc_id):
    doc = get_document(doc_id)
    if doc:
        db_session.query(UploadedDocument).update({"is_active": False})
        doc.is_active = True
        db_session.commit()
        flash(f"'{doc.original_name}' is now the active template.", "success")
    return redirect(url_for("documents.analyzer", doc=doc_id))


@bp.route("/documents/<int:doc_id>/delete", methods=["POST"])
def delete_document(doc_id):
    doc = get_document(doc_id)
    if doc:
        try:
            os.remove(document_path(doc))
        except (OSError, ValueError):
            pass
        db_session.delete(doc)
        db_session.commit()
        flash("Uploaded document removed.", "success")
    return redirect(url_for("documents.analyzer"))


# ---------------------------------------------------------------- analyzer
@bp.route("/analyzer")
def analyzer():
    docs = db_session.query(UploadedDocument).order_by(UploadedDocument.id.desc()).all()
    doc = get_document(request.args.get("doc", type=int)) or active_document()
    analysis, error = analysis_for(doc)
    return render_template("document_analyzer.html", docs=docs, doc=doc, analysis=analysis, error=error)


# ---------------------------------------------------------------- field mappings
@bp.route("/mappings", methods=["GET", "POST"])
def mappings():
    if request.method == "POST":
        fields = request.form.getlist("json_field")
        tables = request.form.getlist("word_table")
        columns = request.form.getlist("word_column")
        removed = set(request.form.getlist("remove"))
        rows, problems = [], []
        for i, (f, t, c) in enumerate(zip(fields, tables, columns)):
            f, t, c = f.strip(), t.strip(), c.strip()
            if str(i) in removed or not (f or t or c):
                continue
            if f not in FIELDS:
                problems.append(f"Row {i + 1}: '{f}' is not a known JSON field.")
            elif not t or not c:
                problems.append(f"Row {i + 1}: both the Word table and the Word column are required.")
            elif len(t) > 200 or len(c) > 200:
                problems.append(f"Row {i + 1}: names are too long.")
            else:
                rows.append((f, t, c))
        if problems:
            for p in problems:
                flash(p, "error")
        else:
            replace_all_mappings(db_session, rows)
            flash(f"Saved {len(rows)} field mappings.", "success")
        return redirect(url_for("documents.mappings"))

    doc = active_document()
    analysis, error = analysis_for(doc)
    return render_template("mappings.html", mappings=list_mappings(db_session), analysis=analysis,
                           doc=doc, fields=[(f, FIELD_LABELS[f]) for f in FIELDS])


@bp.route("/mappings/auto", methods=["POST"])
def mappings_auto():
    doc = active_document()
    analysis, error = analysis_for(doc)
    if not analysis:
        flash("Upload a Word document first - mappings are detected from its tables.", "error")
        return redirect(url_for("documents.mappings"))
    detected = auto_detect_mappings(analysis["tables"])
    if not detected:
        flash("No tables with recognisable column headers were found.", "error")
    else:
        replace_all_mappings(db_session, [(m["json_field"], m["word_table"], m["word_column"]) for m in detected])
        flash(f"Detected {len(detected)} mappings from the document. Review and adjust if needed.", "success")
    return redirect(url_for("documents.mappings"))


@bp.route("/mappings/reset", methods=["POST"])
def mappings_reset():
    replace_all_mappings(db_session, DEFAULT_MAPPINGS)
    flash("Mappings reset to the defaults (Attendance and Daily Progress).", "success")
    return redirect(url_for("documents.mappings"))


# ---------------------------------------------------------------- generation
def back_url(draft) -> str:
    return {"json": url_for("json_routes.preview", draft_id=draft.id),
            "extract": url_for("extract.preview", draft_id=draft.id),
            "weekly": url_for("main.weekly_preview", draft_id=draft.id)}.get(
                draft.kind, url_for("documents.generate_page"))


def _read_options(form):
    mode = form.get("mode", "update")
    if mode not in MODES:
        mode = "update"
    policy = form.get("day_policy", "correct")
    if policy not in ("correct", "keep", "cancel"):
        policy = "correct"
    return mode, policy


@bp.route("/generate", methods=["GET", "POST"])
def generate_page():
    """Generate a Word logbook from everything stored in the database."""
    docs = db_session.query(UploadedDocument).order_by(UploadedDocument.id.desc()).all()
    if request.method == "POST":
        try:
            d_from = date.fromisoformat(request.form["date_from"]) if request.form.get("date_from") else None
            d_to = date.fromisoformat(request.form["date_to"]) if request.form.get("date_to") else None
        except ValueError:
            flash("Invalid date range.", "error")
            return redirect(url_for("documents.generate_page"))
        records = entries_as_records(d_from, d_to)
        if not records:
            flash("There are no saved daily entries in that range. Add entries or import JSON first.", "error")
            return redirect(url_for("documents.generate_page"))
        draft = create_draft("db", records, {"source": "database"})
        return _show_plan(draft, request.form)
    return render_template("generate.html", docs=docs, doc=active_document(), modes=MODES,
                           count=len(entries_as_records()))


def _show_plan(draft, form):
    mode, policy = _read_options(form)
    doc = get_document(form.get("doc_id", type=int)) or active_document()
    if doc is None:
        flash("Upload a Word template first.", "error")
        return redirect(url_for("documents.analyzer"))
    if policy == "cancel":
        flash("Import cancelled.", "info")
        return redirect(url_for("json_routes.import_page"))
    flat, tables, validation = resolve_draft(draft, policy, doc)
    if not flat and not tables:
        flash("There are no valid records to insert.", "error")
        return redirect(back_url(draft))
    plan = build_plan(document_path(doc), flat, tables, list_mappings(db_session), mode,
                      get_schedule().start.year)
    return render_template("changes_preview.html", plan=plan, draft=draft, doc=doc, mode=mode,
                           policy=policy, has_work=plan_has_work(plan), back=back_url(draft),
                           modes=MODES, record_count=len({r["date"] for r in flat}
                                                         | {r["date"] for rs in tables.values() for r in rs}))


@bp.route("/generate/<int:draft_id>/preview", methods=["POST"])
def preview_changes(draft_id):
    draft = get_draft(draft_id)
    if draft is None:
        flash("That working set no longer exists.", "error")
        return redirect(url_for("main.index"))
    return _show_plan(draft, request.form)


@bp.route("/generate/<int:draft_id>/confirm", methods=["POST"])
def confirm_generate(draft_id):
    draft = get_draft(draft_id)
    doc = get_document(request.form.get("doc_id", type=int))
    if draft is None or doc is None:
        flash("The working set or template no longer exists.", "error")
        return redirect(url_for("main.index"))
    mode, policy = _read_options(request.form)
    schedule = get_schedule()
    flat, tables, validation = resolve_draft(draft, policy, doc)
    src = document_path(doc)
    plan = build_plan(src, flat, tables, list_mappings(db_session), mode, schedule.start.year)
    if not plan_has_work(plan):
        flash("Nothing would change in the document, so no file was generated.", "warning")
        return redirect(back_url(draft))

    stem = os.path.splitext(secure_filename(doc.original_name) or "Logbook")[0]
    out_name = f"{stem}_Completed.docx"
    out_path = os.path.join(current_app.config["GENERATED_FOLDER"], out_name)
    if os.path.exists(out_path):
        out_name = f"{stem}_Completed_{timestamp()}.docx"
        out_path = os.path.join(current_app.config["GENERATED_FOLDER"], out_name)
    result = apply_plan(src, out_path, plan, schedule.start.year)

    records = flat + [r for rs in tables.values() for r in rs]
    saved_note = ""
    if request.form.get("also_save") == "1" and records:
        created, updated = upsert_entries(records, schedule)
        saved_note = f" {created} new and {updated} existing database entries were saved."
    if draft.kind == "json":
        log_json_import(records, "Inserted into Word document", draft.source_text)
    log_history(doc.original_name, "generate", result["applied"], "Successful", records,
                {"mode": mode, "stats": plan["stats"], "warnings": result["warnings"]}, out_name)
    return render_template("success.html", title="Document generated",
                           message=f"{result['applied']} date(s) were written to a new copy of your "
                                   f"template.{saved_note} The original file was not changed.",
                           download=url_for("documents.download", kind="generated", filename=out_name),
                           download_name=out_name, stats=plan["stats"], warnings=result["warnings"]
                           + [i["text"] for i in plan["issues"] if i["level"] in ("warning", "error")],
                           roundtrip=url_for("extract.round_trip", draft_id=draft.id, doc_id=doc.id),
                           extract=url_for("extract.extract_page"))


# ---------------------------------------------------------------- downloads
@bp.route("/download/<kind>/<path:filename>")
def download(kind, filename):
    folders = {"generated": current_app.config["GENERATED_FOLDER"],
               "exports": current_app.config["EXPORT_FOLDER"]}
    if kind not in folders or filename != secure_filename(filename):
        abort(404)
    return send_from_directory(folders[kind], filename, as_attachment=True)
