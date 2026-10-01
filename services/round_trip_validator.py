"""Round-trip check: records -> Word -> records, then compare.

A temporary copy of the template is filled (Add-missing-rows mode), read back with the
extractor, and the two sets of records are compared field by field.
"""
import os
import tempfile
from datetime import date

from .common import FIELDS, FIELD_LABELS, clean_ws, long_date, normalize_time
from .document_analyzer import analyze_document
from .document_extractor import extract_records
from .field_mapper import build_targets, mapped_fields_of
from .word_generator import apply_plan, build_plan, merge_by_date, plan_has_work


def _equal(field, a, b) -> bool:
    if field in ("check_in", "check_out"):
        return normalize_time(a)[0] == normalize_time(b)[0]
    return clean_ws(a) == clean_ws(b)


def run_round_trip(template_path, flat_records, table_records, mappings, default_year=None) -> dict:
    expected = merge_by_date(flat_records)
    for rows in (table_records or {}).values():
        for rec in rows:
            expected.setdefault(rec["date"], {}).update({k: v for k, v in rec.items() if v != ""})

    report = {"ok": False, "records": len(expected), "found": 0, "missing_dates": [], "fields": [],
              "warnings": ["Word formatting (fonts, colours, borders) is not represented in JSON."],
              "errors": []}
    if not expected:
        report["errors"].append("There are no records to test.")
        return report

    plan = build_plan(template_path, flat_records, table_records, mappings, "add", default_year)
    for issue in plan["issues"]:
        if issue["level"] == "error":
            report["errors"].append(issue["text"])
    if not plan_has_work(plan):
        report["errors"].append("Nothing could be inserted into the template, so there is nothing to read back.")
        return report

    tmp_dir = tempfile.mkdtemp(prefix="roundtrip_")
    tmp_file = os.path.join(tmp_dir, "roundtrip.docx")
    try:
        apply_plan(template_path, tmp_file, plan, default_year)
        extracted = extract_records(tmp_file, mappings, default_year, skip_empty=False)
        analysis = analyze_document(tmp_file, default_year)
        targets, _ = build_targets(analysis["tables"], mappings, include_auto=True)
        representable = mapped_fields_of(targets)
    finally:
        try:
            os.remove(tmp_file)
            os.rmdir(tmp_dir)
        except OSError:
            pass

    got = {r["date"]: r for r in extracted["records"]}
    report["missing_dates"] = [d for d in sorted(expected) if d not in got]
    report["found"] = len(expected) - len(report["missing_dates"])

    for field in [f for f in FIELDS if f != "date"] + ["date"]:
        total = sum(1 for rec in expected.values() if rec.get(field))
        if total == 0:
            continue
        entry = {"field": field, "label": FIELD_LABELS[field], "total": total, "preserved": 0,
                 "diffs": [], "status": "ok"}
        if field not in representable and field != "date":
            entry["status"] = "unmapped"
            entry["diffs"].append("No Word column is mapped to this field, so it cannot be stored in Word.")
            report["fields"].append(entry)
            continue
        for iso, rec in sorted(expected.items()):
            if not rec.get(field):
                continue
            back = got.get(iso, {}).get(field, "") if field != "date" else (iso if iso in got else "")
            if _equal(field, rec[field], back):
                entry["preserved"] += 1
            elif len(entry["diffs"]) < 5:
                entry["diffs"].append(f"{iso}: '{rec[field]}' became '{back}'")
        if entry["preserved"] != entry["total"]:
            entry["status"] = "changed"
        report["fields"].append(entry)
    report["fields"].sort(key=lambda e: FIELDS.index(e["field"]))

    if report["missing_dates"]:
        shown = ", ".join(long_date(date.fromisoformat(d)) for d in report["missing_dates"][:8])
        report["warnings"].append("Records not found after reading the document back: " + shown)
    report["ok"] = not report["errors"] and not report["missing_dates"] and \
        all(f["status"] in ("ok", "unmapped") for f in report["fields"])
    return report
