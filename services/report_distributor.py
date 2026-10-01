"""Splits one weekly progress report into logical daily entries.

How it works
------------
1. The weekly text is split into topics (commas, semicolons, new lines, bullets).
2. If there are fewer topics than working days, topics joined by "and" are split too.
3. Topics are grouped, in order, as evenly as possible over the week's working days.
4. If there are still more days than topics, the extra days become practice / review days
   that revisit earlier topics (the same text is never copied into every day).
5. Domain and tools are guessed from keywords. Everything can be edited afterwards.
"""
import re

from .common import DAY_NAMES, clean_ws

LEADING_VERBS = re.compile(
    r"^(learned|learnt|learning|worked on|working on|studied|implemented|built|created|"
    r"explored|completed|practiced|practised|understood|developed)\s+(about\s+|how to\s+)?",
    re.I)

DOMAIN_KEYWORDS = [
    (("physics", "rigidbody", "collision", "collider", "force", "gravity", "projectile"),
     "Physics Programming"),
    (("ui", "canvas", "button", "score", "scoring", "menu", "hud"), "UI Development"),
    (("camera", "cinemachine"), "Camera Systems"),
    (("movement", "input", "controller", "player", "jump"), "Gameplay Programming"),
    (("animation", "animator"), "Animation"),
    (("audio", "sound", "music"), "Audio"),
    (("database", "sql", "sqlite"), "Databases"),
    (("api", "flask", "django", "http", "web"), "Web Development"),
    (("test", "debug", "build", "review", "bug"), "Testing & Debugging"),
    (("editor", "setup", "install", "project", "gameobject", "component", "scene",
      "hierarchy", "basics", "interface"), "Unity Fundamentals"),
]

KNOWN_TOOLS = ["Unity", "C#", "Rigidbody", "Visual Studio", "VS Code", "Git", "GitHub",
               "Python", "Flask", "Django", "Blender", "Photoshop", "Cinemachine",
               "Animator", "Collider", "Canvas", "TextMeshPro", "SQLite", "HTML", "CSS",
               "JavaScript", "Java", "Android Studio", "Figma", "Excel", "Word"]


def _strip_verb(topic: str) -> str:
    return LEADING_VERBS.sub("", clean_ws(topic)).strip(" .")


def split_topics(text: str, minimum: int = 1) -> list:
    """Split text into topics; split on 'and' only when more topics are needed."""
    chunks = re.split(r"[\n;•]+|(?:^|\s)[-*]\s+|,\s*(?:and\s+)?|\.\s+(?=[A-Z])", text or "")
    topics = [_strip_verb(c) for c in chunks if _strip_verb(c)]
    if len(topics) < minimum:
        refined = []
        for t in topics:
            parts = [p for p in re.split(r"\s+(?:and|&)\s+", t) if p.strip()]
            refined.extend(parts if len(parts) > 1 else [t])
        topics = refined
    return topics


def _group(topics: list, days: int) -> list:
    """Evenly split `topics` into `days` contiguous groups (some may be empty)."""
    n = len(topics)
    base, extra = divmod(n, days)
    start = (days - extra + 1) // 2  # the busier days sit in the middle of the week
    sizes = [base + (1 if start <= i < start + extra else 0) for i in range(days)]
    groups, pos = [], 0
    for size in sizes:
        groups.append(topics[pos:pos + size])
        pos += size
    return groups


def _join(items: list) -> str:
    items = [i for i in items if i]
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    return ", ".join(items[:-1]) + " and " + items[-1]


def _cap(text: str) -> str:
    return text[:1].upper() + text[1:] if text else text


def guess_domain(text: str) -> str:
    words = set(re.findall(r"[a-z]+", text.lower()))
    for keys, domain in DOMAIN_KEYWORDS:
        if words & set(keys):
            return domain
    return "Software Development"


PLATFORM_TOOLS = {"Unity", "C#", "Python", "Flask", "Django", "Blender", "Visual Studio", "VS Code",
                  "Git", "GitHub", "Photoshop", "Figma", "Android Studio", "SQLite", "HTML",
                  "CSS", "JavaScript", "Java"}

PRACTICE_TEMPLATES = [
    ("Hands-on practice and revision of {0}.", "Strengthened understanding of {0} through practice."),
    ("Debugging and testing work related to {0}.", "Learned how to find and fix problems in {0}."),
    ("Documentation and review of {0}.", "Learned to document and review work on {0}."),
]


def _find_tools(text: str) -> list:
    low = text.lower()
    return [tool for tool in KNOWN_TOOLS
            if re.search(r"(?<![a-z0-9])" + re.escape(tool.lower()) + r"(?![a-z0-9])", low)]


def guess_tools(text: str, base_tools: str = "", platform_from: str = "") -> str:
    """Tools for one day: the user's technologies + tools named in `text`.

    Platform tools (Unity, C#, Python ...) named anywhere in `platform_from` are added to
    every day, because they are used all week.
    """
    found = []

    def add(item):
        item = clean_ws(item)
        if item and item.lower() not in [f.lower() for f in found]:
            found.append(item)

    for item in re.split(r"[,;/\n]+", base_tools or ""):
        add(item)
    for tool in _find_tools(platform_from):
        if tool in PLATFORM_TOOLS:
            add(tool)
    for tool in _find_tools(text):
        add(tool)
    return ", ".join(found)


def distribute_week(week: int, days: list, project: str, progress: str,
                    technologies: str = "", learning_outcomes: str = "",
                    check_in: str = "09:00 AM", check_out: str = "05:00 PM") -> list:
    """Return one record (dict) for each working day in `days` (list of date objects)."""
    if not days:
        return []
    topics = split_topics(progress, minimum=len(days))
    if not topics:
        topics = [clean_ws(progress)] if clean_ws(progress) else []
    outcomes = [o for o in split_topics(learning_outcomes) if o] if learning_outcomes else []

    groups = _group(topics, len(days)) if len(topics) >= len(days) else \
        [[t] for t in topics] + [[] for _ in range(len(days) - len(topics))]

    records = []
    seen = []  # topics already covered, used for practice/review days
    extra_days = 0
    for i, d in enumerate(days):
        group = groups[i] if i < len(groups) else []
        last_day = i == len(days) - 1
        if group:
            seen.extend(group)
            what = _join(group)
            task = f"Worked on {what}."
            learning = f"Learned {what}."
            text_for_guess = " ".join(group)
        else:
            pool = seen or ([project] if project else ["the week's work"])
            topic = pool[extra_days % len(pool)]
            template = PRACTICE_TEMPLATES[extra_days % len(PRACTICE_TEMPLATES)]
            extra_days += 1
            task = template[0].format(topic)
            learning = template[1].format(topic)
            text_for_guess = topic
        if last_day and not re.search(r"test|review", task, re.I):
            task = task[:-1] + ", followed by weekly review and testing."
        if outcomes and group:
            # Use a user-supplied learning outcome when there is one for this day.
            learning = outcomes[min(i, len(outcomes) - 1)] if len(outcomes) >= len(days) \
                else learning
        records.append({
            "date": d.isoformat(), "day": DAY_NAMES[d.weekday()],
            "check_in": check_in, "check_out": check_out,
            "task": _cap(task), "project": project,
            "domain": guess_domain(text_for_guess + " " + project),
            "tools": guess_tools(text_for_guess + " " + (project or ""), technologies,
                                 platform_from=progress),
            "learning": _cap(learning), "notes": "",
        })
    return records
