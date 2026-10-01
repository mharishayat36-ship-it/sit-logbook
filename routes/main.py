"""Dashboard, manual daily entry, weekly report, entries list, history and small JSON APIs."""
import json
from datetime import date

from flask import (Blueprint, Response, current_app, flash, jsonify, redirect, render_template,
                   request, url_for)
from sqlalchemy import func

from models import (DailyEntry, DocumentHistory, JsonImport, WeeklyReport, db_session)
from services import exporter
from services.common import FIELDS, long_date
from services.json_validator import validate_record_dict
from services.report_distributor import distribute_week
from routes.helpers import (active_document, create_draft, entries_as_records, get_draft,
                            get_schedule, prune_old_drafts, upsert_entries)

bp = Blueprint("main", __name__)


# ---------------------------------------------------------------- dashboard
@bp.route("/")
def index():
    schedule = get_schedule()
    today = date.today()
    stats = {
        "weeks": schedule.total_weeks,
        "working_days": schedule.total_working_days(),
        "entries": db_session.query(func.count(DailyEntry.id)).scalar(),
        "weekly_reports": db_session.query(func.count(WeeklyReport.id)).scalar(),
        "json_records": db_session.query(func.coalesce(func.sum(JsonImport.record_count), 0)).scalar(),
        "generated": db_session.query(func.count(DocumentHistory.id)).filter(
            DocumentHistory.operation == "generate", DocumentHistory.status.like("Success%")).scalar(),
    }
    last_import = db_session.query(JsonImport).order_by(JsonImport.id.desc()).first()
    last_extract = db_session.query(DocumentHistory).filter_by(operation="extract") \
        .order_by(DocumentHistory.id.desc()).first()
    return render_template("index.html", stats=stats, today_info=schedule.info(today),
                           today=today, last_import=last_import, last_extract=last_extract,
                           doc=active_document())


# ---------------------------------------------------------------- small APIs
@bp.route("/api/day-info")
def api_day_info():
    try:
        d = date.fromisoformat(request.args.get("date", ""))
    except ValueError:
        return jsonify({"ok": False, "error": "Invalid date"}), 400
    info = get_schedule().info(d)
    info["ok"] = True
    return jsonify(info)


@bp.route("/api/week-info")
def api_week_info():
    try:
        week = int(request.args.get("week", ""))
        if not 1 <= week <= 60:
            raise ValueError
    except ValueError:
        return jsonify({"ok": False, "error": "Week must be a number from 1 to 60."}), 400
    schedule = get_schedule()
    days = schedule.working_days(week)
    return jsonify({"ok": True, "week": week, "count": len(days),
                    "saturday": schedule.saturday_active(week),
                    "days": [{"date": d.isoformat(), "label": long_date(d), "day": schedule.info(d)["day"]}
                             for d in days]})


# ---------------------------------------------------------------- manual daily entry
def _entry_form_values(source) -> dict:
    return {f: (source.get(f, "") or "").strip() for f in FIELDS}


@bp.route("/daily", methods=["GET", "POST"])
@bp.route("/daily/<int:entry_id>", methods=["GET", "POST"])
def daily_entry(entry_id=None):
    schedule = get_schedule()
    entry = db_session.get(DailyEntry, entry_id) if entry_id else None
    if entry_id and entry is None:
        flash("That entry does not exist.", "error")
        return redirect(url_for("main.entries"))
    cfg = current_app.config
    if request.method == "POST":
        values = _entry_form_values(request.form)
        result = validate_record_dict(values, schedule)
        errors = [m["text"] for m in result["messages"] if m["level"] == "error"]
        if errors:
            for e in errors:
                flash(e, "error")
            return render_template("daily_entry.html", values=values, entry=entry,
                                   week_info=None, defaults=cfg)
        rec = result["record"]
        if result["day_mismatch"]:
            rec["day"] = result["day_calc"]
            flash(f"The day was corrected to {result['day_calc']} to match the date.", "warning")
        for m in result["messages"]:
            if m["level"] == "warning" and "supplied day" not in m["text"]:
                flash(m["text"], "warning")
        d = date.fromisoformat(rec["date"])
        clash = db_session.query(DailyEntry).filter_by(date=d).first()
        if entry is None and clash is not None:
            entry = clash
            flash(f"An entry for {long_date(d)} already existed and was updated.", "info")
        if entry is None:
            entry = DailyEntry(date=d)
            db_session.add(entry)
        elif clash is not None and clash.id != entry.id:
            flash(f"Another entry already exists for {long_date(d)}.", "error")
            return render_template("daily_entry.html", values=values, entry=entry,
                                   week_info=None, defaults=cfg)
        entry.date = d
        entry.week_number = schedule.week_of(d)
        for f in FIELDS:
            if f != "date":
                setattr(entry, f, rec.get(f, ""))
        db_session.commit()
        flash(f"Saved the entry for {long_date(d)} (week {entry.week_number}).", "success")
        return redirect(url_for("main.entries"))

    if entry:
        values = entry.to_dict()
    else:
        values = {f: "" for f in FIELDS}
        values["check_in"], values["check_out"] = cfg["DEFAULT_CHECK_IN"], cfg["DEFAULT_CHECK_OUT"]
        values["date"] = request.args.get("date", "")
    return render_template("daily_entry.html", values=values, entry=entry, defaults=cfg)


@bp.route("/entries")
def entries():
    rows = db_session.query(DailyEntry).order_by(DailyEntry.date).all()
    return render_template("entries.html", rows=rows)


@bp.route("/entries/<int:entry_id>/delete", methods=["POST"])
def delete_entry(entry_id):
    entry = db_session.get(DailyEntry, entry_id)
    if entry:
        db_session.delete(entry)
        db_session.commit()
        flash("Entry deleted.", "success")
    return redirect(url_for("main.entries"))


@bp.route("/entries/export/<fmt>")
def export_entries(fmt):
    from routes.extract_routes import send_export
    return send_export(entries_as_records(), fmt, "logbook_entries")


# ---------------------------------------------------------------- weekly report
@bp.route("/weekly", methods=["GET", "POST"])
def weekly_report():
    schedule = get_schedule()
    cfg = current_app.config
    reports = db_session.query(WeeklyReport).order_by(WeeklyReport.week_number).all()
    if request.method == "POST":
        form = {k: (request.form.get(k, "") or "").strip() for k in
                ("week", "project", "progress", "technologies", "learning_outcomes", "notes",
                 "check_in", "check_out")}
        values = dict(form, action=request.form.get("action", "distribute"))
        try:
            week = int(form["week"])
            if not 1 <= week <= 60:
                raise ValueError
        except ValueError:
            flash("Week must be a whole number from 1 to 60.", "error")
            return render_template("weekly_report.html", values=values, reports=reports, defaults=cfg)
        if not form["progress"]:
            flash("Please describe the weekly progress.", "error")
            return render_template("weekly_report.html", values=values, reports=reports, defaults=cfg)

        report = db_session.query(WeeklyReport).filter_by(week_number=week).first() or WeeklyReport(week_number=week)
        report.project, report.weekly_progress = form["project"], form["progress"]
        report.technologies, report.learning_outcomes = form["technologies"], form["learning_outcomes"]
        report.notes = form["notes"]
        db_session.add(report)
        db_session.commit()

        if values["action"] == "save":
            flash(f"Weekly report for week {week} saved.", "success")
            return redirect(url_for("main.weekly_report"))

        days = schedule.working_days(week)
        records = distribute_week(week, days, form["project"], form["progress"], form["technologies"],
                                  form["learning_outcomes"], form["check_in"] or cfg["DEFAULT_CHECK_IN"],
                                  form["check_out"] or cfg["DEFAULT_CHECK_OUT"])
        draft = create_draft("weekly", records, {"week": week, "project": form["project"]})
        prune_old_drafts()
        return redirect(url_for("main.weekly_preview", draft_id=draft.id))

    values = {"week": request.args.get("week", ""), "project": "", "progress": "", "technologies": "",
              "learning_outcomes": "", "notes": "", "check_in": cfg["DEFAULT_CHECK_IN"],
              "check_out": cfg["DEFAULT_CHECK_OUT"]}
    load = request.args.get("load", type=int)
    if load:
        r = db_session.query(WeeklyReport).filter_by(week_number=load).first()
        if r:
            values.update(week=r.week_number, project=r.project, progress=r.weekly_progress,
                          technologies=r.technologies, learning_outcomes=r.learning_outcomes,
                          notes=r.notes)
    return render_template("weekly_report.html", values=values, reports=reports, defaults=cfg)


@bp.route("/weekly/preview/<int:draft_id>")
def weekly_preview(draft_id):
    draft = get_draft(draft_id)
    if draft is None or draft.kind != "weekly":
        flash("That weekly preview no longer exists.", "error")
        return redirect(url_for("main.weekly_report"))
    schedule = get_schedule()
    meta = draft.meta
    return render_template("weekly_preview.html", draft=draft, records=draft.records, meta=meta,
                           week_days=[long_date(date.fromisoformat(r["date"])) for r in draft.records],
                           saturday=schedule.saturday_active(meta.get("week", 0)),
                           doc=active_document())


# ---------------------------------------------------------------- history
@bp.route("/history")
def history():
    tab = request.args.get("tab", "imports")
    imports = db_session.query(JsonImport).order_by(JsonImport.id.desc()).limit(200).all()
    ops = db_session.query(DocumentHistory).order_by(DocumentHistory.id.desc()).limit(300).all()
    extractions = [o for o in ops if o.operation == "extract"]
    documents = [o for o in ops if o.operation != "extract"]
    for o in ops:
        try:
            o.parsed = json.loads(o.details or "{}")
        except ValueError:
            o.parsed = {}
    return render_template("history.html", tab=tab, imports=imports, extractions=extractions,
                           documents=documents)
