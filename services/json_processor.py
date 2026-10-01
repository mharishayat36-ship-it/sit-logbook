"""Parsing pasted JSON into a uniform internal structure.

Accepted inputs
---------------
1. one object            {"date": ..., "task": ...}
2. an array of objects   [{...}, {...}]
3. table-specific object {"tables": {"Attendance": [{...}], "Daily Progress": [{...}]}}
   (a flat "records": [...] list may sit next to "tables")
"""
import json
import re

from .common import FIELDS, date_range_label, key_to_field


def _clean_for_retry(text: str) -> str:
    """Fix common copy/paste problems: ``` fences, smart quotes, trailing commas."""
    t = text.strip().lstrip("﻿")
    t = re.sub(r"^```[a-zA-Z]*\s*", "", t)
    t = re.sub(r"\s*```$", "", t)
    t = t.replace("“", '"').replace("”", '"').replace("‘", "'").replace("’", "'")
    t = re.sub(r",\s*([}\]])", r"\1", t)
    return t


def parse_json_text(text: str, max_chars: int = 2_000_000) -> dict:
    """Returns {'ok', 'error', 'items', 'notes'}.

    items = list of {'scope': None | table name, 'raw': <whatever the JSON had>}
    """
    out = {"ok": False, "error": None, "items": [], "notes": []}
    if text is None or not text.strip():
        out["error"] = "No JSON was supplied. Paste a JSON object or array."
        return out
    if len(text) > max_chars:
        out["error"] = "The JSON text is too large."
        return out
    data, first_error = None, None
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        first_error = f"JSON syntax error at line {exc.lineno}, column {exc.colno}: {exc.msg}"
        try:
            data = json.loads(_clean_for_retry(text))
            out["notes"].append("The JSON had small formatting problems (quotes, commas or "
                                "code fences) that were fixed automatically.")
        except json.JSONDecodeError:
            out["error"] = first_error
            return out
    except RecursionError:
        out["error"] = "The JSON is nested too deeply."
        return out

    if isinstance(data, list):
        out["items"] = [{"scope": None, "raw": r} for r in data]
    elif isinstance(data, dict):
        has_container = "tables" in data or "records" in data
        if has_container:
            tables = data.get("tables")
            if tables is not None:
                if not isinstance(tables, dict):
                    out["error"] = "'tables' must be an object: {\"Table name\": [records]}."
                    return out
                for name, rows in tables.items():
                    if isinstance(rows, dict):
                        rows = [rows]
                    if not isinstance(rows, list):
                        out["error"] = f"Table '{name}' must contain an array of records."
                        return out
                    out["items"].extend({"scope": str(name), "raw": r} for r in rows)
            recs = data.get("records")
            if recs is not None:
                if isinstance(recs, dict):
                    recs = [recs]
                if not isinstance(recs, list):
                    out["error"] = "'records' must be an array of objects."
                    return out
                out["items"].extend({"scope": None, "raw": r} for r in recs)
        else:
            out["items"] = [{"scope": None, "raw": data}]
    else:
        out["error"] = "The JSON must be an object or an array of objects."
        return out
    if not out["items"]:
        out["error"] = "The JSON contains no records."
        return out
    out["ok"] = True
    return out


def normalize_record(raw: dict):
    """Map alias keys to canonical fields and coerce values to text.

    Returns (record, issues). `issues` is a list of (level, text).
    """
    record = {f: "" for f in FIELDS}
    issues = []
    for key, value in raw.items():
        field = key_to_field(key)
        if field is None:
            issues.append(("warning", f"Unknown field '{key}' was ignored."))
            continue
        if value is None:
            text = ""
        elif isinstance(value, bool):
            issues.append(("error", f"Field '{key}' must be text, not true/false."))
            continue
        elif isinstance(value, (str, int, float)):
            text = str(value).strip()
        elif isinstance(value, list) and all(isinstance(v, (str, int, float)) for v in value):
            text = ", ".join(str(v).strip() for v in value)
            issues.append(("info", f"Field '{key}' was a list and was joined with commas."))
        else:
            issues.append(("error", f"Field '{key}' has an unsupported data type "
                                    f"({type(value).__name__}); use plain text."))
            continue
        if record[field] and text and record[field] != text:
            issues.append(("warning", f"Field '{field}' was supplied twice; the last value was used."))
        if text or not record[field]:
            record[field] = text
    return record, issues


def records_date_range(records) -> str:
    return date_range_label([r.get("date") for r in records])


def pretty_json(data) -> str:
    return json.dumps(data, indent=4, ensure_ascii=False)
