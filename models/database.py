"""SQLAlchemy models and session handling."""
import json
from datetime import date, datetime
from typing import Optional

from sqlalchemy import Boolean, Date, DateTime, Integer, String, Text, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, scoped_session, sessionmaker

# One scoped session for the whole app. It is bound to an engine in init_db().
db_session = scoped_session(sessionmaker(autoflush=False, expire_on_commit=False))


class Base(DeclarativeBase):
    pass


class Internship(Base):
    __tablename__ = "internship"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(200), default="Internship Training Logbook")
    start_date: Mapped[date] = mapped_column(Date)
    total_weeks: Mapped[int] = mapped_column(Integer, default=16)


class WeeklyReport(Base):
    __tablename__ = "weekly_report"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    week_number: Mapped[int] = mapped_column(Integer, unique=True)
    project: Mapped[str] = mapped_column(String(300), default="")
    weekly_progress: Mapped[str] = mapped_column(Text, default="")
    technologies: Mapped[str] = mapped_column(Text, default="")
    learning_outcomes: Mapped[str] = mapped_column(Text, default="")
    notes: Mapped[str] = mapped_column(Text, default="")


class DailyEntry(Base):
    __tablename__ = "daily_entry"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    week_number: Mapped[int] = mapped_column(Integer, default=0)
    date: Mapped[date] = mapped_column(Date, unique=True)
    day: Mapped[str] = mapped_column(String(20), default="")
    check_in: Mapped[str] = mapped_column(String(20), default="")
    check_out: Mapped[str] = mapped_column(String(20), default="")
    task: Mapped[str] = mapped_column(Text, default="")
    project: Mapped[str] = mapped_column(String(300), default="")
    domain: Mapped[str] = mapped_column(String(300), default="")
    tools: Mapped[str] = mapped_column(Text, default="")
    learning: Mapped[str] = mapped_column(Text, default="")
    notes: Mapped[str] = mapped_column(Text, default="")

    def to_dict(self):
        return {
            "date": self.date.isoformat(), "day": self.day or "",
            "check_in": self.check_in or "", "check_out": self.check_out or "",
            "task": self.task or "", "project": self.project or "",
            "domain": self.domain or "", "tools": self.tools or "",
            "learning": self.learning or "", "notes": self.notes or "",
        }


class JsonImport(Base):
    __tablename__ = "json_import"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    imported_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    record_count: Mapped[int] = mapped_column(Integer, default=0)
    date_range: Mapped[str] = mapped_column(String(100), default="")
    status: Mapped[str] = mapped_column(String(200), default="")
    source_data: Mapped[str] = mapped_column(Text, default="")


class FieldMapping(Base):
    __tablename__ = "field_mapping"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    json_field: Mapped[str] = mapped_column(String(50))
    word_table: Mapped[str] = mapped_column(String(200))
    word_column: Mapped[str] = mapped_column(String(200))


class DocumentHistory(Base):
    """History of document operations: 'generate', 'extract', 'round-trip'."""
    __tablename__ = "document_history"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    filename: Mapped[str] = mapped_column(String(300))
    operation: Mapped[str] = mapped_column(String(50))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    record_count: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(200), default="")
    date_range: Mapped[str] = mapped_column(String(100), default="")
    details: Mapped[str] = mapped_column(Text, default="")
    output_file: Mapped[str] = mapped_column(String(300), default="")


class UploadedDocument(Base):
    """A Word file the user uploaded. The stored file is never modified."""
    __tablename__ = "uploaded_document"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    original_name: Mapped[str] = mapped_column(String(300))
    stored_name: Mapped[str] = mapped_column(String(300), unique=True)
    size: Mapped[int] = mapped_column(Integer, default=0)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)


class Draft(Base):
    """A temporary working set of records (JSON paste, extraction result, weekly distribution)."""
    __tablename__ = "draft"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[str] = mapped_column(String(30))  # json | extract | weekly | db
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    records_json: Mapped[str] = mapped_column(Text, default="[]")
    meta_json: Mapped[str] = mapped_column(Text, default="{}")
    source_text: Mapped[str] = mapped_column(Text, default="")

    @property
    def records(self) -> list:
        return json.loads(self.records_json or "[]")

    @records.setter
    def records(self, value: list):
        self.records_json = json.dumps(value, ensure_ascii=False)

    @property
    def meta(self) -> dict:
        return json.loads(self.meta_json or "{}")

    @meta.setter
    def meta(self, value: dict):
        self.meta_json = json.dumps(value, ensure_ascii=False)


def init_db(database_uri: str):
    """Create the engine, bind the session and create all tables."""
    engine = create_engine(database_uri, connect_args={"check_same_thread": False})
    db_session.configure(bind=engine)
    Base.metadata.create_all(engine)
    return engine
