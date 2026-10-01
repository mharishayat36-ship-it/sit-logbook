"""Field mapping: which JSON field goes into which Word table and column.

Mappings live in the SQLite table `field_mapping` and are edited on the Mappings page.
"""
from collections import OrderedDict

from .common import FIELD_LABELS, FIELDS, auto_columns, norm

DEFAULT_MAPPINGS = [
    ("date", "Attendance", "Date"), ("day", "Attendance", "Day"),
    ("check_in", "Attendance", "Check In"), ("check_out", "Attendance", "Check Out"),
    ("date", "Daily Progress", "Date"), ("task", "Daily Progress", "Task"),
    ("project", "Daily Progress", "Project"), ("domain", "Daily Progress", "Domain"),
    ("tools", "Daily Progress", "Tools"), ("learning", "Daily Progress", "Learning"),
]


# ---------------------------------------------------------------- database access
def seed_default_mappings(session):
    from models import FieldMapping
    if session.query(FieldMapping).count() == 0:
        for f, t, c in DEFAULT_MAPPINGS:
            session.add(FieldMapping(json_field=f, word_table=t, word_column=c))
        session.commit()


def list_mappings(session) -> list:
    from models import FieldMapping
    rows = session.query(FieldMapping).order_by(FieldMapping.id).all()
    return [{"id": r.id, "json_field": r.json_field, "word_table": r.word_table,
             "word_column": r.word_column} for r in rows]


def replace_all_mappings(session, rows):
    """Replace every mapping with `rows` (list of (field, table, column))."""
    from models import FieldMapping
    session.query(FieldMapping).delete()
    for f, t, c in rows:
        session.add(FieldMapping(json_field=f, word_table=t, word_column=c))
    session.commit()


# ---------------------------------------------------------------- matching tables
def find_matching_tables(query, tables) -> list:
    """Tables of the document that a mapping/JSON table name refers to.

    Matches the table's heading/name, its guessed type ('Attendance', 'Daily Progress'),
    or 'Table 2' / '2'. If several tables share a name (e.g. one table per week) all match.
    """
    q = norm(query)
    if not q:
        return []
    exact, loose = [], []
    for t in tables:
        names = [norm(t["name"]), norm(t["heading"]), norm(t["guess"])]
        numeric = {norm(f"Table {t['number']}"), str(t["number"])}
        if q in numeric or q in [n for n in names if n]:
            exact.append(t)
        elif len(q) >= 4 and any(n and len(n) >= 4 and (q in n or n in q) for n in names):
            loose.append(t)
    return exact or loose


def resolve_column_index(headers, wanted):
    """Index of the column whose header matches `wanted` (exact first, then contains)."""
    w = norm(wanted)
    if not w:
        return None
    for i, h in enumerate(headers):
        if norm(h) == w:
            return i
    if len(w) >= 3:
        for i, h in enumerate(headers):
            n = norm(h)
            if n and len(n) >= 3 and (w in n or n in w):
                return i
    return None


def auto_detect_mappings(tables) -> list:
    """Build mapping rows from the headers of each table: [{'json_field','word_table','word_column'}]."""
    rows = []
    for t in tables:
        cols = auto_columns(t["columns"])
        if "date" not in cols or len(cols) < 2:
            continue
        for field in FIELDS:
            if field in cols:
                rows.append({"json_field": field, "word_table": t["guess"] or t["name"],
                             "word_column": t["columns"][cols[field]]})
    # drop duplicates produced by several tables with the same type (one table per week)
    seen, unique = set(), []
    for r in rows:
        key = (r["json_field"], norm(r["word_table"]), norm(r["word_column"]))
        if key not in seen:
            seen.add(key)
            unique.append(r)
    return unique


def mappings_match_document(mappings, tables) -> bool:
    return any(find_matching_tables(m["word_table"], tables) for m in mappings)


# ---------------------------------------------------------------- building targets
def build_targets(tables, mappings, extra_names=(), include_auto=False):
    """Work out where each field goes in the document.

    Returns (targets, issues). A target is one *logical* table: a mapping table name plus every
    Word table it matches, with `columns[table_index] = {field: column_index}`.
    """
    issues = []
    targets = []
    covered = set()

    by_name = OrderedDict()
    for m in mappings:
        by_name.setdefault(m["word_table"], []).append(m)

    for name, rows in by_name.items():
        matched = find_matching_tables(name, tables)
        if not matched:
            issues.append({"level": "info", "text":
                           f"Mapping table '{name}' does not exist in this document (ignored)."})
            continue
        target = {"name": name, "table_indexes": [], "columns": {}, "date_cols": {}, "source": "mapping"}
        for t in matched:
            cols = {}
            for m in rows:
                ci = resolve_column_index(t["columns"], m["word_column"])
                if ci is None:
                    issues.append({"level": "error", "text":
                                   f"Field '{m['json_field']}': no Word column named '{m['word_column']}' "
                                   f"was found in table '{t['name']}'. Action: configure field mapping."})
                else:
                    cols.setdefault(m["json_field"], ci)
            date_col = cols.get("date", t["date_col"])
            if date_col is None:
                issues.append({"level": "error", "text":
                               f"Table '{t['name']}' has no date column; it cannot be used."})
                continue
            cols.setdefault("date", date_col)
            target["table_indexes"].append(t["index"])
            target["columns"][t["index"]] = cols
            target["date_cols"][t["index"]] = date_col
            covered.add(t["index"])
        if target["table_indexes"]:
            targets.append(target)

    def auto_target(t, source):
        cols = auto_columns(t["columns"])
        date_col = cols.get("date", t["date_col"])
        if date_col is None or len(cols) < 1:
            return None
        cols.setdefault("date", date_col)
        return {"name": t["name"], "table_indexes": [t["index"]], "columns": {t["index"]: cols},
                "date_cols": {t["index"]: date_col}, "source": source}

    for name in extra_names:
        for t in find_matching_tables(name, tables):
            if t["index"] not in covered:
                tg = auto_target(t, "json")
                if tg:
                    targets.append(tg)
                    covered.add(t["index"])
                else:
                    issues.append({"level": "error", "text":
                                   f"Table '{t['name']}' has no usable date/field columns."})
    if include_auto:
        for t in tables:
            if t["index"] not in covered:
                tg = auto_target(t, "auto")
                if tg and len(tg["columns"][t["index"]]) >= 2:
                    targets.append(tg)
                    covered.add(t["index"])
    return targets, issues


def mapped_fields_of(targets) -> set:
    fields = set()
    for t in targets:
        for cols in t["columns"].values():
            fields |= set(cols)
    return fields


def target_matches_name(name, target, tables) -> bool:
    """Does a table-specific JSON key refer to this target?"""
    idx = {t["index"] for t in find_matching_tables(name, tables)}
    return bool(idx & set(target["table_indexes"]))


def field_label(field):
    return FIELD_LABELS.get(field, field)
