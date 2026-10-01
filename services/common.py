"""Shared helpers: field definitions, date/time parsing and formatting, header matching.

Everything here is locale-independent (we never use strftime for names) so the
program behaves the same on every Windows language setting.
"""
import re
from datetime import date

FIELDS = ["date", "day", "check_in", "check_out", "task", "project",
          "domain", "tools", "learning", "notes"]
CORE_FIELDS = FIELDS[:9]  # the nine fields used in the simple JSON format
FIELD_LABELS = {
    "date": "Date", "day": "Day", "check_in": "Check In", "check_out": "Check Out",
    "task": "Task", "project": "Project", "domain": "Domain", "tools": "Tools",
    "learning": "Learning", "notes": "Notes",
}
TEXT_FIELDS = ["task", "project", "domain", "tools", "learning", "notes"]

DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
MONTH_NAMES = ["January", "February", "March", "April", "May", "June", "July",
               "August", "September", "October", "November", "December"]
MONTH_ABBR = [m[:3] for m in MONTH_NAMES]


def norm(text) -> str:
    """Lower-case and strip everything except letters and digits."""
    return re.sub(r"[^a-z0-9]", "", str(text or "").lower())


def clean_ws(text) -> str:
    return " ".join(str(text or "").split())


# ---------------------------------------------------------------- header matching
# EXACT: the whole (normalised) header must equal one of these.
# CONTAINS: the (normalised) header may merely contain one of these (>= 4 chars).
EXACT = {
    "date": ["date", "dates", "dateofentry"],
    "day": ["day", "days", "weekday", "dayname", "dayofweek"],
    "check_in": ["in", "timein", "checkin", "intime"],
    "check_out": ["out", "timeout", "checkout", "outtime"],
    "task": ["activity", "activities", "work", "workdone"],
    "project": [], "domain": [], "tools": [], "learning": [], "notes": [],
}
CONTAINS = {
    "date": ["date"],
    "day": [],
    "check_in": ["checkin", "intime", "timein", "arrival", "starttime"],
    "check_out": ["checkout", "outtime", "timeout", "departure", "endtime"],
    "task": ["task", "workdone", "workdescription"],
    "project": ["project"],
    "domain": ["domain", "nature"],
    "tools": ["tools", "technolog"],
    "learning": ["learning", "learnt", "conclusion", "outcome"],
    "notes": ["notes", "note", "remark", "comment"],
}


def match_field(header):
    """Return (field, score) for a Word column header, or (None, 0)."""
    h = norm(header)
    if not h:
        return None, 0
    for field, words in EXACT.items():
        if h in words:
            return field, 1000 + len(h)
    best, best_len = None, 0
    for field, words in CONTAINS.items():
        for w in words:
            if w in h and len(w) > best_len:
                best, best_len = field, len(w)
    return best, best_len


def auto_columns(headers):
    """Map field -> column index by reading header texts left to right."""
    found = {}
    for idx, header in enumerate(headers):
        field, _ = match_field(header)
        if field and field not in found:
            found[field] = idx
    return found


def key_to_field(key):
    """Translate a JSON key (e.g. 'Check In', 'check_in', 'tasks') to a field name."""
    h = norm(key)
    if not h:
        return None
    for field in FIELDS:
        if h == norm(field):
            return field
    for field, words in list(EXACT.items()) + list(CONTAINS.items()):
        if h in words:
            return field
    extra = {"tasks": "task", "taskassigned": "task", "tasksassigned": "task",
             "tasknature": "domain", "toolsused": "tools", "learnings": "learning",
             "projectname": "project", "remarks": "notes"}
    return extra.get(h)


# ---------------------------------------------------------------- dates
_ISO_RE = re.compile(r"^\s*(\d{4})-(\d{1,2})-(\d{1,2})\s*$")


def parse_iso_strict(text):
    """Returns ('ok', date) | ('format', None) | ('invalid', None)."""
    m = _ISO_RE.match(str(text or ""))
    if not m:
        return "format", None
    try:
        return "ok", date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return "invalid", None


def _month_from_name(word):
    w = word.lower()[:3]
    for i, m in enumerate(MONTH_ABBR):
        if m.lower() == w:
            return i + 1
    return None


def _year(y, default_year):
    if y is None or y == "":
        return default_year
    y = int(y)
    return 2000 + y if y < 100 else y


def parse_date(text, default_year=None):
    """Parse many human date formats into a date (or None).

    Understands: 2026-09-28, 28/09/2026, 28-09-2026, 28.09.2026, 28 Sep 2026,
    28th September 2026, September 28, 2026, Sep 28 2026, Monday, 28 Sep 2026,
    and (when default_year is given) '28 Sep'.
    """
    s = clean_ws(text)
    if not s:
        return None
    s = re.sub(r"\b(" + "|".join(DAY_NAMES + [d[:3] for d in DAY_NAMES]) + r")\b\.?,?", " ",
               s, flags=re.I)
    s = re.sub(r"(?<=\d)(st|nd|rd|th)\b", "", s, flags=re.I)
    s = clean_ws(s)
    try:
        m = re.search(r"(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})", s)
        if m:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        m = re.search(r"(\d{1,2})[-/.](\d{1,2})[-/.](\d{2,4})", s)
        if m:
            a, b, y = int(m.group(1)), int(m.group(2)), _year(m.group(3), default_year)
            if b > 12 >= a:  # clearly month/day/year
                a, b = b, a
            return date(y, b, a)
        m = re.search(r"(\d{1,2})\s*([A-Za-z]{3,9})\.?,?\s*(\d{4})?", s)
        if m and _month_from_name(m.group(2)):
            y = _year(m.group(3), default_year)
            if y:
                return date(y, _month_from_name(m.group(2)), int(m.group(1)))
        m = re.search(r"([A-Za-z]{3,9})\.?\s+(\d{1,2}),?\s*(\d{4})?", s)
        if m and _month_from_name(m.group(1)):
            y = _year(m.group(3), default_year)
            if y:
                return date(y, _month_from_name(m.group(1)), int(m.group(2)))
    except ValueError:
        return None
    return None


DATE_STYLES = {
    "dd Mon yyyy": lambda d: f"{d.day:02d} {MONTH_ABBR[d.month - 1]} {d.year}",
    "dd Month yyyy": lambda d: f"{d.day:02d} {MONTH_NAMES[d.month - 1]} {d.year}",
    "dd-mm-yyyy": lambda d: f"{d.day:02d}-{d.month:02d}-{d.year}",
    "dd/mm/yyyy": lambda d: f"{d.day:02d}/{d.month:02d}/{d.year}",
    "dd.mm.yyyy": lambda d: f"{d.day:02d}.{d.month:02d}.{d.year}",
    "yyyy-mm-dd": lambda d: d.isoformat(),
    "Month dd, yyyy": lambda d: f"{MONTH_NAMES[d.month - 1]} {d.day:02d}, {d.year}",
    "Mon dd, yyyy": lambda d: f"{MONTH_ABBR[d.month - 1]} {d.day:02d}, {d.year}",
}
DEFAULT_DATE_STYLE = "dd Mon yyyy"


def format_date(d, style=DEFAULT_DATE_STYLE):
    return DATE_STYLES.get(style, DATE_STYLES[DEFAULT_DATE_STYLE])(d)


def detect_date_style(text):
    """Guess which style an existing Word date cell uses (None if unknown)."""
    s = clean_ws(text)
    s = re.sub(r"^(" + "|".join(DAY_NAMES) + r"),?\s*", "", s, flags=re.I)
    if re.match(r"^\d{4}-\d{1,2}-\d{1,2}", s):
        return "yyyy-mm-dd"
    if re.match(r"^\d{1,2}-\d{1,2}-\d{4}", s):
        return "dd-mm-yyyy"
    if re.match(r"^\d{1,2}/\d{1,2}/\d{4}", s):
        return "dd/mm/yyyy"
    if re.match(r"^\d{1,2}\.\d{1,2}\.\d{4}", s):
        return "dd.mm.yyyy"
    m = re.match(r"^\d{1,2}(?:st|nd|rd|th)?\s+([A-Za-z]{3,9})\.?,?\s+\d{4}", s)
    if m:
        return "dd Mon yyyy" if len(m.group(1)) == 3 else "dd Month yyyy"
    m = re.match(r"^([A-Za-z]{3,9})\.?\s+\d{1,2},?\s+\d{4}", s)
    if m:
        return "Mon dd, yyyy" if len(m.group(1)) == 3 else "Month dd, yyyy"
    return None


def day_name(d):
    return DAY_NAMES[d.weekday()]


def long_date(d):
    return f"{d.day} {MONTH_NAMES[d.month - 1]} {d.year}"


def short_date(d):
    return f"{d.day:02d} {MONTH_ABBR[d.month - 1]}"


def parse_day_name(text):
    """'mon', 'Monday', 'MONDAY' -> 'Monday'; anything else -> None."""
    t = clean_ws(text).lower().rstrip(".")
    if len(t) < 3:
        return None
    for name in DAY_NAMES:
        if name.lower() == t or (len(t) == 3 and name.lower()[:3] == t):
            return name
    return None


def date_range_label(isos):
    """['2026-09-28', ...] -> '28 Sep – 03 Oct 2026'."""
    ds = []
    for i in isos:
        try:
            ds.append(date.fromisoformat(i))
        except (TypeError, ValueError):
            pass
    if not ds:
        return ""
    lo, hi = min(ds), max(ds)
    if lo == hi:
        return long_date(lo)
    return f"{short_date(lo)} {lo.year} – {short_date(hi)} {hi.year}" if lo.year != hi.year \
        else f"{short_date(lo)} – {short_date(hi)} {hi.year}"


# ---------------------------------------------------------------- times
def normalize_time(text):
    """Returns (value, ok). '9am' -> ('09:00 AM', True); '' -> ('', True); 'abc' -> ('abc', False)."""
    s = clean_ws(text)
    if not s:
        return "", True
    m = re.match(r"^(\d{1,2})(?:[:.](\d{2}))?\s*([AaPp])?\.?[Mm]?\.?$", s)
    if not m:
        return s, False
    hour, minute = int(m.group(1)), int(m.group(2) or 0)
    suffix = {"A": "AM", "P": "PM"}.get((m.group(3) or "").upper(), "")
    if minute > 59:
        return s, False
    if suffix:
        if not 1 <= hour <= 12:
            return s, False
    else:
        if hour > 23:
            return s, False
        suffix = "PM" if hour >= 12 else "AM"
        hour = hour - 12 if hour > 12 else (12 if hour == 0 else hour)
    return f"{hour:02d}:{minute:02d} {suffix}", True


def time_minutes(value):
    """'05:00 PM' -> 1020 (minutes since midnight) or None."""
    v, ok = normalize_time(value)
    if not ok or not v:
        return None
    hh, rest = v.split(":")
    mm, suffix = rest.split(" ")
    hh = int(hh) % 12 + (12 if suffix == "PM" else 0)
    return hh * 60 + int(mm)
