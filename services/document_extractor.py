"""Word -> JSON: reads every mapped table and combines the rows that share a date."""
from datetime import date

from docx import Document

from .common import (FIELDS, clean_ws, day_name, long_date, normalize_time, parse_date,
                     parse_day_name)
from .document_analyzer import analyze_loaded
from .field_mapper import build_targets
from .word_utils import row_texts

# Fields we warn about when they are empty (only if some table actually has that column).
WARN_IF_EMPTY = ["check_in", "check_out", "task", "project", "domain", "tools", "learning"]
LABEL = {"check_in": "Check-in", "check_out": "Check-out", "task": "Task", "project": "Project",
         "domain": "Domain", "tools": "Tools", "learning": "Learning"}


def extract_records(doc_path, mappings, default_year=None, skip_empty=True) -> dict:
    """Extract records from every table that can be matched to fields.

    Uses explicit mappings first; tables not covered by a mapping are auto-detected from their
    column headers. Returns {'records', 'messages', 'tables_used', 'stats'}.
    messages = [{'date', 'level', 'text'}]
    """
    doc = Document(doc_path)
    tables = analyze_loaded(doc, default_year)
    word_tables = doc.tables
    targets, issues = build_targets(tables, mappings, include_auto=True)
    messages = [{"date": "", "level": i["level"], "text": i["text"]} for i in issues
                if i["level"] != "info"]
    out = {"records": [], "messages": messages, "tables_used": [],
           "stats": {"rows_read": 0, "rows_skipped": 0, "empty_dropped": 0}}
    if not tables:
        messages.append({"date": "", "level": "error", "text": "The document contains no tables."})
        return out
    if not targets:
        messages.append({"date": "", "level": "error", "text":
                         "No table with a date column was found. Check the Field Mapping page."})
        return out

    by_date = {}      # iso -> {field: value}
    sources = {}      # iso -> {field: table name} (for conflict messages)
    available = set()

    for target in targets:
        for ti in target["table_indexes"]:
            table, info = word_tables[ti], tables[ti]
            cols = target["columns"][ti]
            dc = target["date_cols"][ti]
            available |= set(cols)
            used = {"name": info["name"], "index": ti, "mapping": target["name"],
                    "fields": [f for f in FIELDS if f in cols], "rows": 0}
            trs = table._tbl.tr_lst
            for r in range(info["header_row"] + 1, len(trs)):
                texts = row_texts(trs[r], table)
                if not any(t.strip() for t in texts):
                    continue
                out["stats"]["rows_read"] += 1
                raw_date = texts[dc] if dc < len(texts) else ""
                d = parse_date(raw_date, default_year)
                values = {f: (texts[c].strip() if c < len(texts) else "")
                          for f, c in cols.items() if f != "date"}
                if d is None:
                    if any(v for v in values.values()):
                        out["stats"]["rows_skipped"] += 1
                        messages.append({"date": "", "level": "warning", "text":
                            f"Table '{info['name']}', row {r + 1}: the date "
                            f"'{clean_ws(raw_date) or '(empty)'}' could not be read. Row skipped."})
                    continue
                iso = d.isoformat()
                used["rows"] += 1
                rec = by_date.setdefault(iso, {})
                src = sources.setdefault(iso, {})
                for f, v in values.items():
                    if not v:
                        continue
                    if f in ("check_in", "check_out"):
                        v2, ok = normalize_time(v)
                        if not ok:
                            messages.append({"date": iso, "level": "warning", "text":
                                f"{long_date(d)}: {LABEL[f]} '{v}' is not a recognised time; kept as is."})
                        v = v2
                    if f == "day":
                        dn = parse_day_name(v)
                        if dn and dn != day_name(d):
                            messages.append({"date": iso, "level": "warning", "text":
                                f"{long_date(d)} is {day_name(d)}, but the document says {v}."})
                        v = dn or v
                    if rec.get(f) and clean_ws(rec[f]) != clean_ws(v):
                        messages.append({"date": iso, "level": "warning", "text":
                            f"{long_date(d)}: '{f}' differs between '{src.get(f)}' and "
                            f"'{info['name']}'; the first value was kept."})
                        continue
                    if not rec.get(f):
                        rec[f] = v
                        src[f] = info["name"]
            out["tables_used"].append(used)

    records = []
    for iso in sorted(by_date):
        d = date.fromisoformat(iso)
        rec = {f: "" for f in FIELDS}
        rec.update(by_date[iso])
        rec["date"] = iso
        if not rec["day"]:
            rec["day"] = day_name(d)
        has_data = any(rec[f] for f in FIELDS if f not in ("date", "day"))
        if not has_data and skip_empty:
            out["stats"]["empty_dropped"] += 1
            continue
        for f in WARN_IF_EMPTY:
            if f in available and not rec[f] and has_data:
                messages.append({"date": iso, "level": "warning", "text":
                                 f"{long_date(d)}: {LABEL[f]} field is empty."})
        records.append(rec)
    out["records"] = records
    return out
