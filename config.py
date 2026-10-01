"""Application configuration. Edit the values below to suit your internship."""
import os
from datetime import date

BASE_DIR = os.path.abspath(os.path.dirname(__file__))


class Config:
    # Used to sign flash messages. Set LOGBOOK_SECRET_KEY in your environment for real use.
    SECRET_KEY = os.environ.get("LOGBOOK_SECRET_KEY", "dev-secret-change-me")

    # Database (SQLite file in the project folder)
    DATABASE_PATH = os.path.join(BASE_DIR, "database.db")
    DATABASE_URI = "sqlite:///" + DATABASE_PATH.replace("\\", "/")

    # Controlled folders. Uploaded files are NEVER executed and NEVER overwritten.
    UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")
    GENERATED_FOLDER = os.path.join(BASE_DIR, "generated")
    EXPORT_FOLDER = os.path.join(BASE_DIR, "exports")

    # Upload limits
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16 MB
    ALLOWED_EXTENSIONS = {"docx"}
    MAX_JSON_CHARS = 2_000_000

    # Internship settings (stored in the database on first run, editable there later)
    INTERNSHIP_TITLE = "Internship Training Logbook"
    INTERNSHIP_START = date(2026, 8, 31)  # Monday
    TOTAL_WEEKS = 16

    # Defaults for new entries
    DEFAULT_CHECK_IN = "09:00 AM"
    DEFAULT_CHECK_OUT = "05:00 PM"
