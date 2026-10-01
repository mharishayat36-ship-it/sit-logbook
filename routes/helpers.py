"""Helpers shared by all route modules (database look-ups, drafts, history)."""
import json
import os
from datetime import date, datetime

from flask import current_app

from models import (DailyEntry, DocumentHistory, Draft, Internship, JsonImport,
                    UploadedDocument, db_session)
from services.common import FIELDS, date_range_label, day_name
from services.document_analyzer import analyze_document
from services.field_mapper import (build_targets, find_matching_tables, list_mappings,
                                   mapped_fields_of)
from services.json_processor import parse_json_text
from services.json_validator import usable_records, validate_parsed
from services.schedule_generator import Schedule


# ---------------------------------------------------------------- internship / schedule
def get_internship() -> Internship:
    internship = db_session.query(Internship).first()
    if internship is None:
        cfg = current_app.config
        internship = Internship(title=cfg["INTERNSHIP_TITLE"], start_date=cfg["INTERNSHIP_START"],
                                total_weeks=cfg["TOTAL_WEEKS"])
        db_session.add(internship)
        db_session.commit()
    return internship


def get_schedule() -> Schedule:
    i = get_internship()
    return Schedule(i.start_date, i.total_weeks)


# ---------------------------------------------------------------- uploaded documents
def active_document():
    return db_session.query(UploadedDocument).filter_by(is_active=True).first()


def get_document(doc_id):
    if not doc_id:
        return None
    try:
        return db_session.get(UploadedDocument, int(doc_id))
    except (TypeError, ValueError):
        return None


def document_path(doc) -> str:
    """Absolute path of an uploaded document (always inside the uploads folder)."""
    folder = os.path.abspath(current_app.config["UPLOAD_FOLDER"])
    path = os.path.abspath(os.path.join(folder, doc.stored_name))
    if os.path.dirname(path) != folder:
        raise ValueError("Invalid document path.")
    return path


def analysis_for(doc):
    """(analysis, error_message). Never raises."""
    if doc is None:
        return None, None
    try:
        return analyze_document(document_path(doc), get_schedule().start.year), None
    except Exception as exc:  # corrupted/odd documents must not crash the page
        return None, f"The document could not be analysed: {exc}"


# ---------------------------------------------------------------- JSON validation with document context
def validate_json_text(text, doc=None):
    """Parse + validate pasted JSON. Returns (parsed, validation or None)."""
    parsed = parse_json_text(text, current_app.config["MAX_JSON_CHARS"])
    if not parsed["ok"]:
        return parsed, None
    schedule = get_schedule()
    tables, mapped = None, None
    if doc is not None:
        analysis, _ = analysis_for(doc)
        if analysis:
            tables = analysis["tables"]
            scopes = sorted({i["scope"] for i in parsed["items"] if i["scope"]})
            targets, _ = build_targets(tables, list_mappings(db_session), extra_names=scopes)
            mapped = mapped_fields_of(targets)
    return parsed, validate_parsed(parsed, schedule, tables, mapped, find_matching_tables)


def resolve_draft(draft, policy="correct", doc=None):
    """Return (flat_records, table_records, validation_or_None) for any kind of draft."""
    if draft.kind == "json":
        parsed, validation = validate_json_text(draft.source_text, doc)
        if validation is None:
            return [], {}, None
        flat, tables = usable_records(validation, policy)
        return flat, tables, validation
    return list(draft.records), {}, None


# ---------------------------------------------------------------- drafts
def create_draft(kind, records=None, meta=None, source_text=""):
    draft = Draft(kind=kind, source_text=source_text)
    draft.records = records or []
    draft.meta = meta or {}
    db_session.add(draft)
    db_session.commit()
    return draft


def get_draft(draft_id):
    return db_session.get(Draft, draft_id)


def prune_old_drafts(keep=200):
    """Keep the draft table small: remove all but the newest `keep` drafts."""
    ids = [d.id for d in db_session.query(Draft.id).order_by(Draft.id.desc()).offset(keep).all()]
    if ids:
        db_session.query(Draft).filter(Draft.id.in_(ids)).delete(synchronize_session=False)
        db_session.commit()


# ---------------------------------------------------------------- daily entries
def upsert_entries(records, schedule, overwrite_blank=False):
    """Insert or merge records into daily_entry by date. Returns (created, updated)."""
    created = updated = 0
    for rec in records:
        try:
            d = date.fromisoformat(rec["date"])
        except (KeyError, ValueError):
            continue
        entry = db_session.query(DailyEntry).filter_by(date=d).first()
        if entry is None:
            entry = DailyEntry(date=d)
            db_session.add(entry)
            created += 1
        else:
            updated += 1
        entry.week_number = schedule.week_of(d)
        entry.day = rec.get("day") or entry.day or day_name(d)
        for f in FIELDS:
            if f in ("date", "day"):
                continue
            value = rec.get(f, "")
            if value or overwrite_blank:
                setattr(entry, f, value)
    db_session.commit()
    return created, updated


def entries_as_records(date_from=None, date_to=None):
    q = db_session.query(DailyEntry).order_by(DailyEntry.date)
    if date_from:
        q = q.filter(DailyEntry.date >= date_from)
    if date_to:
        q = q.filter(DailyEntry.date <= date_to)
    return [e.to_dict() for e in q.all()]


# ---------------------------------------------------------------- history
def log_history(filename, operation, record_count, status, records=None, details=None, output_file=""):
    row = DocumentHistory(
        filename=filename, operation=operation, record_count=record_count, status=status,
        date_range=date_range_label([r.get("date") for r in (records or [])]),
        details=json.dumps(details or {}, ensure_ascii=False), output_file=output_file)
    db_session.add(row)
    db_session.commit()
    return row


def log_json_import(records, status, source_text):
    row = JsonImport(record_count=len(records), status=status, source_data=source_text or "",
                     date_range=date_range_label([r.get("date") for r in records]))
    db_session.add(row)
    db_session.commit()
    return row


def timestamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")
