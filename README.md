# Internship Training Logbook Automation System

A Flask web application that works as a **two-way bridge between a Word `.docx` logbook and structured JSON data**.

```
Word document  →  Extract  →  JSON / CSV / Excel
JSON / forms / weekly report  →  Validate  →  Preview  →  Word document
```

Everything runs on your own computer at `http://127.0.0.1:5000`. Your original Word file is **never modified** – results are always written to a new `..._Completed.docx`.

---

## 1. Windows setup

Open PowerShell in the project folder (the folder that contains `app.py`).

> **Keep the folder path short** (for example `C:\logbook_automation` or `Documents\logbook_automation`). Windows can fail to load Python's compiled packages from extremely long paths.

**1. Create a virtual environment**

```powershell
python -m venv venv
```

**2. Activate it**

```powershell
venv\Scripts\activate
```

**3. Install the dependencies**

```powershell
pip install -r requirements.txt
```

**4. Start the application**

```powershell
python app.py
```

**5. Open the website**

```
http://127.0.0.1:5000
```

Stop the server with `Ctrl + C`. Next time, only repeat steps 2 and 4.

### If PowerShell refuses to activate the virtual environment

The error looks like *"running scripts is disabled on this system"*. Allow scripts for your user account only:

```powershell
Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
```

Answer `Y`, then run `venv\Scripts\activate` again. Alternatively use **Command Prompt** (`cmd`) instead of PowerShell, or skip activation and call Python directly:

```powershell
venv\Scripts\python.exe app.py
```

### Try it with a sample logbook

```powershell
python create_sample_template.py
```

This creates `sample_templates\Internship_Training_Logbook_Sample.docx` (an *Attendance* table and a *Daily Progress* table with dates pre-filled for weeks 1–4). Upload it on the **Analyzer** page.

### Run the self-test (optional)

```powershell
python selftest.py
```

It drives the whole application (upload, JSON → Word, Word → JSON, exports, weekly report, security checks) using a temporary database and prints `PASS`/`FAIL` for each check. Your real data is not touched.

---

## 2. Architecture and data flow

```
 Browser (HTML/CSS/JS, Jinja2)
        │
        ▼
 routes/            Flask blueprints (thin: read the form, call services, render a page)
   main.py            dashboard, daily entry, weekly report, entries, history
   json_routes.py     paste JSON → validate → preview → save
   extract_routes.py  Word → JSON, editable preview, exports, round-trip
   documents.py       upload, analyzer, field mapping, generate, download
   helpers.py         shared database look-ups
        │
        ▼
 services/          all the real logic (no Flask code)
   schedule_generator.py   working-day calendar (5/6-day alternating weeks)
   report_distributor.py   weekly report → daily entries
   json_processor.py       parse pasted JSON (object / array / table-specific)
   json_validator.py       syntax, dates, weekdays, duplicates, fields, tables
   document_analyzer.py    find tables, header rows, columns, date column
   field_mapper.py         JSON field → Word table → Word column
   word_generator.py       build a change plan, then apply it to a copy
   document_extractor.py   read the tables and merge rows by date
   round_trip_validator.py JSON → Word → JSON comparison
   exporter.py             JSON / CSV / Excel
   word_utils.py, common.py  low-level Word-XML and date/time helpers
        │
        ▼
 models/database.py   SQLAlchemy + SQLite (database.db)
 uploads/ generated/ exports/   controlled file folders
```

**The three data-entry paths all end in the same place:** a list of *records* (one per date) that is validated and then either saved to the database, inserted into Word, or exported.

```
Manual form ───────┐
Weekly report ─────┼──►  records  ──►  validation  ──►  preview  ──►  Word copy / database
JSON paste ────────┘                                         ▲
Word tables ──► extract ──► editable table ──► JSON/CSV/Excel ┘
```

### Safety by design: two-step Word writing
1. `build_plan()` is **read-only**. It works out exactly which cells will change (old → new) and shows them to you.
2. Only after you press **Confirm and Generate** does `apply_plan()` reload the original template, apply the plan and save a *new* file.

---

## 3. Internship calendar

* Start: **Monday 31 August 2026** (change it in `config.py` *before the first run*, or in the `internship` table of `database.db` later).
* Mon–Fri are always working days. **Saturday works in even weeks only** (week 2, 4, 6 …). **Sunday is never a working day.**
* Week 1 = 5 days, week 2 = 6 days, week 3 = 5 days, week 4 = 6 days …

All of this is calculated with Python `datetime`; there are no hard-coded dates apart from the start date. The default length is 16 weeks (`TOTAL_WEEKS` in `config.py`).

---

## 4. Using the application

### Workflow A – JSON → Word
1. **Analyzer** → upload your `.docx` template. The tables and columns are shown. Mappings are detected automatically if none of the saved ones fit.
2. **Field Mapping** → check which JSON field goes into which table/column (optional).
3. **Import JSON** → paste JSON → *Validate & preview*.
4. Review the ✓ / ⚠ / ✗ list. If the `day` does not match the `date`, choose **Correct automatically**, **Keep the supplied value** or **Cancel import**.
5. Choose an insertion mode and press **Insert Into Document**.
6. Review every cell that will change → **Confirm and Generate** → download the new file.

(Alternatively press **Save to Database** to keep the records without touching Word.)

### Workflow B – Word → JSON
1. **Extract Word** → upload/select a logbook that already contains data.
2. Check the detected tables → **Extract records**. Rows from different tables with the same date are merged into one record.
3. Review warnings (for example *"Learning field is empty"*) and **edit the table**: change cells, add or delete records, **Save changes**.
4. **Copy JSON**, or download **JSON / CSV / Excel**. You can also save to the database or generate a Word file from the same data.

### Workflow C – Weekly report → Word
1. **Weekly Report** → enter the week number, project and a progress summary → *Distribute across days*.
2. Check the generated daily entries (Mon–Fri, or Mon–Sat in even weeks), edit if you want.
3. **Save to database** and/or **Preview Word changes** → confirm.

### Manual entry
**Daily Entry** → pick a date (day name and week number appear automatically) → save. Saved entries are listed on **Entries** (edit, delete, export) and can be written to Word from **Generate**.

### Insertion modes
| Mode | If the date is already in the Word table | If the date is NOT in the Word table |
|---|---|---|
| **Update existing rows only** | row is updated | record is skipped (reported) |
| **Add missing rows** | row is updated | an empty row is filled, otherwise a new row (copy of a neighbouring row's formatting) is inserted in date order |
| **Strict** | row is updated | reported as an error, nothing changed for that record |

Dates are matched after normalising, so `2026-09-28` matches `28 Sep 2026`, `28-09-2026`, `28/09/2026` and `September 28, 2026`. New rows use the same date style as the existing rows.

---

## 5. JSON formats

**One record** (only `date` is required):

```json
{
    "date": "2026-09-28",
    "day": "Monday",
    "check_in": "09:00 AM",
    "check_out": "05:00 PM",
    "task": "Worked on ball physics and throwing mechanics.",
    "project": "Cup Toss Game",
    "domain": "Physics Programming",
    "tools": "Unity, C#, Rigidbody",
    "learning": "Learned how Rigidbody physics affects projectile movement."
}
```

**Many records:** put them in an array `[ {...}, {...} ]`.

**Table-specific** (for documents with several tables):

```json
{
    "tables": {
        "Attendance": [ { "date": "2026-09-28", "day": "Monday", "check_in": "09:00 AM", "check_out": "05:00 PM" } ],
        "Daily Progress": [ { "date": "2026-09-28", "task": "Worked on ball physics.", "project": "Cup Toss Game" } ]
    }
}
```

A flat record fills **every** table that has matching columns. A table-specific record fills only that table.

Also accepted: key aliases (`tasks`, `check in`, `conclusion` …), times such as `9am` / `17:00` (normalised to `09:00 AM`), JSON pasted inside ``` fences, smart quotes and trailing commas.

### What the validator checks
JSON syntax (with line/column) · object/array structure · required `date` · date format and real calendar validity (`2026-09-31` is rejected) · weekday vs date · duplicate dates · unknown fields · empty values · data types · time formats · working-day status · target table names · fields that have no Word column.

---

## 6. How Word tables are recognised

* Every top-level table is analysed: header row (searched in the first 6 rows, so a merged title row above the header is fine), column names, date column (by header, or by looking at the cell contents), empty rows, merged cells.
* A table's name is the paragraph/heading right above it, or a guess from its columns (`Attendance`, `Daily Progress`). In mappings you may use either, or `Table 2`.
* **Several tables with the same name** (for example one table per week) are treated as one group; the date decides which table is used.
* **Merged cells:** horizontally merged cells are handled; the continuation cells of a *vertical* merge are never written (a warning is shown instead of corrupting the document).
* Formatting is preserved: only the text of the target cell is replaced, keeping the first run's font/size/bold, paragraph alignment, borders, headers, footers, page layout.

---

## 7. Project structure

```
logbook_automation/
├── app.py                  entry point (python app.py)
├── config.py               settings (start date, weeks, limits, defaults)
├── requirements.txt
├── create_sample_template.py   makes a practice .docx
├── selftest.py             end-to-end self test
├── database.db             created on first run
├── models/                 SQLAlchemy models
├── services/               business logic (see section 2)
├── routes/                 Flask blueprints
├── templates/              Jinja2 pages
├── static/css, static/js   styling and browser scripts
├── uploads/                your uploaded templates (never modified)
├── generated/              generated Word files
├── exports/                JSON/CSV/Excel exports
└── sample_templates/
```

### Database tables (SQLite)
`internship`, `weekly_report`, `daily_entry`, `json_import`, `field_mapping`, `document_history`, plus two helper tables: `uploaded_document` (your templates) and `draft` (temporary working sets for previews).

---

## 8. Security

Only `.docx` is accepted and the file must really be a valid Word package · 16 MB upload limit · filenames sanitised and stored under a random prefix · files stored only in `uploads/`, `generated/`, `exports/` · uploaded files are never executed or overwritten · downloads are restricted to those folders · all HTML output is escaped (Jinja2) · malformed JSON is handled with clear messages.

The server listens on `127.0.0.1` only (your own computer). Don't expose it to a network without adding login and CSRF protection. Set `LOGBOOK_SECRET_KEY` as an environment variable for a private session key.

---

## 9. Limitations and tips

* Only **table-based** logbooks are supported. If your Word file uses free-form pages (no tables with a date column) the analyzer will tell you; use the Field Mapping page or restructure the template.
* JSON stores text only: **Word formatting is not represented in JSON** (the round-trip report says so).
* Multi-paragraph/rich content inside a cell is replaced by plain text with line breaks.
* Back up `database.db` occasionally – it holds your daily entries and history.
* If a mapped column is not found you get an explicit message (field, reason, action) instead of a silent failure.

## 10. Troubleshooting

| Problem | Fix |
|---|---|
| `python` is not recognised | Install Python 3 from python.org and tick **Add Python to PATH**. |
| *running scripts is disabled* | See the execution-policy fix in section 1. |
| `ImportError: DLL load failed ... filename or extension is too long` | Move the project to a shorter path such as `C:\logbook_automation` and recreate the `venv`. |
| *No Word table matches the field mappings* | Open **Field Mapping** → **Auto-detect mappings**. |
| Port 5000 already in use | Close the other program, or change `port=5000` at the bottom of `app.py`. |
