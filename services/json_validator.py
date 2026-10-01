"""Validation of parsed JSON records. Nothing here touches the Word document."""
from datetime import date

from .common import (FIELDS, day_name, long_date, normalize_time, parse_date, parse_day_name,
                     parse_iso_strict, time_minutes)
from .json_processor import normalize_record

REQUIRED_FIELDS = ["date"]


def validate_item(item, schedule, seen_dates, default_year=None):
    """Validate one parsed item and return a result dict (see validate_parsed)."""
    scope = item.get("scope")
    raw = item.get("raw")
    res = {"scope": scope, "label": "(no date)", "status": "ok", "messages": [],
           "record": None, "day_supplied": "", "day_calc": "", "day_mismatch": False}

    def msg(level, text):
        res["messages"].append({"level": level, "text": text})

    if not isinstance(raw, dict):
        res["status"] = "error"
        msg("error", "Each record must be a JSON object { ... }.")
        return res

    record, issues = normalize_record(raw)
    for level, text in issues:
        msg(level, text)
    if any(m["level"] == "error" for m in res["messages"]):
        res["status"] = "error"
        res["label"] = record.get("date") or "(no date)"
        return res

    # -- required fields
    for f in REQUIRED_FIELDS:
        if not record.get(f):
            msg("error", f"Required field '{f}' is missing or empty.")
    raw_date = record.get("date", "")
    res["label"] = raw_date or "(no date)"

    d = None
    if raw_date:
        state, parsed = parse_iso_strict(raw_date)
        if state == "ok":
            d = parsed
        elif state == "invalid":
            msg("error", "Invalid calendar date.")
        else:
            d = parse_date(raw_date, default_year)
            if d:
                msg("warning", f"Date '{raw_date}' is not in YYYY-MM-DD format; "
                               f"it was read as {d.isoformat()}.")
            else:
                msg("error", f"Invalid date '{raw_date}'. Use YYYY-MM-DD, e.g. 2026-09-28.")

    if d:
        record["date"] = d.isoformat()
        res["label"] = d.isoformat()
        key = (scope, d)
        if key in seen_dates:
            msg("error", "Duplicate date in this "
                         + (f"table ('{scope}')." if scope else "import.") + " This record is skipped.")
        else:
            seen_dates.add(key)
        calc = day_name(d)
        res["day_calc"] = calc
        supplied = record.get("day", "")
        res["day_supplied"] = supplied
        if not supplied:
            record["day"] = calc
        else:
            parsed_day = parse_day_name(supplied)
            if parsed_day == calc:
                record["day"] = calc
            else:
                res["day_mismatch"] = True
                record["day"] = parsed_day or supplied
                msg("warning", f"{long_date(d)} is {calc}, but the supplied day is {supplied}.")
        info = schedule.info(d)
        if not info["working"]:
            msg("warning", f"{long_date(d)} is not an internship working day ({info['reason']}).")
        elif info["week"] > schedule.total_weeks:
            msg("warning", f"{long_date(d)} is in week {info['week']}, after the planned "
                           f"{schedule.total_weeks} weeks.")

    # -- times
    for f in ("check_in", "check_out"):
        value, ok = normalize_time(record.get(f, ""))
        if ok:
            record[f] = value
        else:
            msg("error", f"Field '{f}' has an invalid time '{value}'. Use e.g. 09:00 AM.")
    a, b = time_minutes(record.get("check_in")), time_minutes(record.get("check_out"))
    if a is not None and b is not None and b <= a:
        msg("warning", "Check-out is not later than check-in.")

    if not any(record.get(f) for f in FIELDS if f not in ("date", "day")):
        msg("warning", "The record has a date but no other data.")

    res["record"] = record
    levels = {m["level"] for m in res["messages"]}
    res["status"] = "error" if "error" in levels else "warning" if "warning" in levels else "ok"
    return res


def validate_parsed(parsed, schedule, doc_tables=None, mapped_fields=None, find_tables=None):
    """Validate everything produced by json_processor.parse_json_text().

    doc_tables / find_tables: when a Word template is active, table names used in
    table-specific JSON are checked against it. find_tables(name, doc_tables) -> list.
    mapped_fields: set of fields that have a Word column; unmapped fields give a global warning.
    Returns {'results': [...], 'global': [...], 'summary': {...}}.
    """
    seen = set()
    results = []
    for item in parsed["items"]:
        res = validate_item(item, schedule, seen, schedule.start.year)
        if item.get("scope") and doc_tables is not None and find_tables is not None:
            if not find_tables(item["scope"], doc_tables):
                names = ", ".join(t["name"] for t in doc_tables) or "none"
                res["messages"].append({"level": "error", "text":
                    f"Target table '{item['scope']}' was not found in the Word document "
                    f"(tables found: {names})."})
                res["status"] = "error"
        results.append(res)

    glob = [{"level": "info", "text": n} for n in parsed.get("notes", [])]
    if doc_tables is None:
        glob.append({"level": "info", "text":
                     "No Word template is selected, so table names and field mappings were not checked."})
    elif mapped_fields is not None:
        used = set()
        for r in results:
            if r["record"] and r["status"] != "error":
                used |= {f for f in FIELDS if r["record"].get(f) and f not in ("date",)}
        for f in sorted(used - set(mapped_fields)):
            glob.append({"level": "warning", "text":
                         f"Field '{f}' has no matching Word column. It will not be written to the "
                         f"document. Action: configure field mapping."})

    summary = {
        "total": len(results),
        "ok": sum(r["status"] == "ok" for r in results),
        "warning": sum(r["status"] == "warning" for r in results),
        "error": sum(r["status"] == "error" for r in results),
        "mismatches": sum(r["day_mismatch"] for r in results),
    }
    summary["usable"] = summary["ok"] + summary["warning"]
    return {"results": results, "global": glob, "summary": summary}


def usable_records(validation, day_policy="correct"):
    """Apply the user's day-mismatch choice and return (flat_records, table_records).

    day_policy: 'correct' -> use the calculated weekday, 'keep' -> keep the supplied one.
    Records with errors are dropped.
    """
    flat, tables = [], {}
    for r in validation["results"]:
        if r["status"] == "error" or not r["record"]:
            continue
        rec = dict(r["record"])
        if r["day_mismatch"] and day_policy == "correct":
            rec["day"] = r["day_calc"]
        if r["scope"]:
            tables.setdefault(r["scope"], []).append(rec)
        else:
            flat.append(rec)
    return flat, tables


def validate_record_dict(raw: dict, schedule):
    """Validate one record coming from a web form (used by the manual-entry page)."""
    return validate_item({"scope": None, "raw": raw}, schedule, set(), schedule.start.year)


def today_default() -> str:
    return date.today().isoformat()
