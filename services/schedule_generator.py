"""Working-day calendar for the internship.

Rules
-----
* Week 1 starts on the internship start date (Monday 31 August 2026).
* Monday-Friday are always working days.
* Saturday is a working day only in EVEN weeks (week 2, 4, 6 ...).
* Sunday is never a working day.

Everything is calculated with datetime arithmetic - no hard-coded dates other than the start.
"""
from datetime import date, timedelta

from .common import DAY_NAMES, day_name

DEFAULT_START = date(2026, 8, 31)


class Schedule:
    def __init__(self, start=DEFAULT_START, total_weeks=16):
        self.start = start
        self.total_weeks = total_weeks
        # Monday of week 1 (equals `start` when the start is a Monday)
        self._week1_monday = start - timedelta(days=start.weekday())

    # -- basic calculations ------------------------------------------------
    def week_of(self, d: date) -> int:
        """Week number of a date (0 if it is before the internship starts)."""
        delta = (d - self._week1_monday).days
        return delta // 7 + 1 if delta >= 0 else 0

    @staticmethod
    def saturday_active(week: int) -> bool:
        return week > 0 and week % 2 == 0

    def is_working_day(self, d: date) -> bool:
        week = self.week_of(d)
        if week == 0 or d < self.start:
            return False
        wd = d.weekday()
        if wd < 5:
            return True
        if wd == 5:
            return self.saturday_active(week)
        return False

    def info(self, d: date) -> dict:
        week = self.week_of(d)
        working = self.is_working_day(d)
        if d < self.start:
            reason = "Before the internship start date"
        elif d.weekday() == 6:
            reason = "Sunday is always off"
        elif d.weekday() == 5 and not self.saturday_active(week):
            reason = "Saturday is off in odd-numbered weeks"
        elif week > self.total_weeks:
            reason = "After the planned internship end"
        else:
            reason = "Working day"
        return {"date": d.isoformat(), "day": day_name(d), "week": week,
                "working": working, "saturday_active": self.saturday_active(week),
                "reason": reason}

    # -- week / schedule helpers --------------------------------------------
    def week_start(self, week: int) -> date:
        return self._week1_monday + timedelta(days=7 * (week - 1))

    def working_days(self, week: int) -> list:
        """List of working dates in a given week (5 or 6 days)."""
        if week < 1:
            return []
        monday = self.week_start(week)
        count = 6 if self.saturday_active(week) else 5
        return [monday + timedelta(days=i) for i in range(count)
                if monday + timedelta(days=i) >= self.start]

    def week_range(self, week: int):
        days = self.working_days(week)
        return (days[0], days[-1]) if days else (None, None)

    def all_working_days(self) -> list:
        out = []
        for w in range(1, self.total_weeks + 1):
            out.extend(self.working_days(w))
        return out

    def total_working_days(self) -> int:
        return len(self.all_working_days())

    def generate_schedule(self) -> list:
        """Full table: one dict per working day of the internship."""
        rows = []
        for w in range(1, self.total_weeks + 1):
            for d in self.working_days(w):
                rows.append({"week": w, "date": d.isoformat(), "day": DAY_NAMES[d.weekday()],
                             "working": True, "saturday_active": self.saturday_active(w)})
        return rows
