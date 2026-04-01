# =============================================================
# api_features.py  —  EduTrack Pro Feature Extensions
#
# FEATURE 1: Department Drill-Down Analytics
#   GET  /api/departments            → list departments with live stats
#   GET  /api/departments/{dept}/courses → courses + stats for dept
#   GET  /api/departments/{dept}/courses/{course}/sections → sections
#   GET  /api/departments/{dept}/courses/{course}/sections/{sec}/students
#            → student list with per-student attendance %
#
# FEATURE 2: Faculty Management
#   GET  /api/faculty                → list all faculty
#   POST /api/faculty                → create faculty record
#   GET  /api/faculty/{fac_id}       → single faculty profile + history
#   GET  /api/faculty/analytics/summary → KPI strip + chart data
#   POST /api/faculty/attendance     → mark faculty attendance
#   PUT  /api/faculty/{fac_id}/attendance/{log_id} → edit log entry
#   DELETE /api/faculty/{fac_id}/attendance/{log_id}
#   GET  /api/faculty/export/csv     → CSV download
#
# All new routes are mounted in create_app() via register_feature_routes()
# and require the same JWT token used by the rest of the system.
# =============================================================

import os
import csv
import io
import sqlite3
import logging
from datetime import datetime, timedelta, date

log = logging.getLogger(__name__)

# ── Dept / Course / Section taxonomy ────────────────────────
# This mirrors what the frontend DEPTS / COURSE_META constants define.
# Departments are derived from the roll_number prefix stored on students
# (e.g. "23CS086" → dept key "CS").  For a fresh install the table has
# no students; the helpers below fall back to a sensible default list so
# the UI always has something to show.
#
# Each student row is expected to carry:
#   section   → "A" | "B" | …
#   roll_number → used to derive dept / course (e.g. "23CS086")
#
# For the Faculty Management feature, faculty records live in the
# `faculty` table (created below if absent) and attendance logs in
# `faculty_attendance`.

# =============================================================
# DB HELPERS
# =============================================================

def _db_path():
    import config
    return os.path.join(config.BASE_DIR, "attendance.db")


def _conn():
    """Open a WAL-mode SQLite connection with Row factory."""
    c = sqlite3.connect(_db_path(), timeout=15, check_same_thread=False)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA foreign_keys=ON")
    return c


def _ensure_faculty_tables():
    """Create faculty & faculty_attendance tables if they don't exist."""
    with _conn() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS faculty (
            fac_id        TEXT PRIMARY KEY,
            name          TEXT NOT NULL,
            dept          TEXT NOT NULL DEFAULT '',
            designation   TEXT NOT NULL DEFAULT 'Assistant Professor',
            email         TEXT,
            mobile        TEXT,
            subjects      TEXT DEFAULT '[]',   -- JSON array stored as text
            joined_on     TEXT,
            active        INTEGER DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS faculty_attendance (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            fac_id      TEXT NOT NULL,
            att_date    TEXT NOT NULL,
            status      TEXT NOT NULL DEFAULT 'present',
            arrival_time TEXT,
            reason      TEXT,
            updated_by  TEXT,
            created_at  TEXT DEFAULT (datetime('now','localtime')),
            UNIQUE(fac_id, att_date)
        );

        CREATE INDEX IF NOT EXISTS idx_fa_date  ON faculty_attendance(att_date);
        CREATE INDEX IF NOT EXISTS idx_fa_facid ON faculty_attendance(fac_id);
        """)
        c.commit()
        _seed_demo_faculty(c)


def _seed_demo_faculty(conn):
    """Insert demo rows only if the faculty table is empty."""
    count = conn.execute("SELECT COUNT(*) FROM faculty").fetchone()[0]
    if count > 0:
        return

    demo = [
        ("FAC001", "Dr. A. Kumar",       "CS",  "Professor",
         "kumar@college.edu",   "9900001111",
         '["Data Structures","Algorithms"]'),
        ("FAC002", "Ms. R. Priya",       "CS",  "Assistant Professor",
         "priya@college.edu",   "9900002222",
         '["Web Technology","DBMS"]'),
        ("FAC003", "Dr. S. Rajan",       "ECE", "Associate Professor",
         "rajan@college.edu",   "9900003333",
         '["DSP","Signals"]'),
        ("FAC004", "Mr. K. Venkat",      "ECE", "Assistant Professor",
         "venkat@college.edu",  "9900004444",
         '["VLSI","Embedded"]'),
        ("FAC005", "Dr. M. Lakshmi",     "MECH","Professor",
         "lakshmi@college.edu", "9900005555",
         '["Thermodynamics","Fluid Mechanics"]'),
        ("FAC006", "Ms. P. Deepa",       "MECH","Assistant Professor",
         "deepa@college.edu",   "9900006666",
         '["CAD","Manufacturing"]'),
        ("FAC007", "Dr. T. Suresh",      "CIVIL","Associate Professor",
         "suresh@college.edu",  "9900007777",
         '["Structural Analysis","RCC Design"]'),
        ("FAC008", "Mr. G. Balamurugan","IT",  "Assistant Professor",
         "bala@college.edu",    "9900008888",
         '["Python Programming","AI"]'),
    ]
    today = datetime.now().strftime("%Y-%m-%d")
    for row in demo:
        try:
            conn.execute(
                "INSERT OR IGNORE INTO faculty"
                " (fac_id,name,dept,designation,email,mobile,subjects,joined_on)"
                " VALUES (?,?,?,?,?,?,?,?)",
                (*row, today)
            )
        except Exception:
            pass

    # Seed ~30 days of random attendance per faculty
    import random
    random.seed(42)
    statuses = ["present"] * 18 + ["present"] * 5 + ["absent"] * 3 + \
               ["late"] * 2 + ["halfday"] * 1 + ["od"] * 1
    for fac_id, *_ in demo:
        for offset in range(30, 0, -1):
            d = (datetime.now() - timedelta(days=offset)).strftime("%Y-%m-%d")
            # Skip weekends
            wday = datetime.strptime(d, "%Y-%m-%d").weekday()
            if wday >= 5:
                continue
            st = random.choice(statuses)
            try:
                conn.execute(
                    "INSERT OR IGNORE INTO faculty_attendance"
                    " (fac_id,att_date,status,arrival_time,updated_by)"
                    " VALUES (?,?,?,?,?)",
                    (fac_id, d, st,
                     "09:05" if st in ("present", "od") else
                     "09:45" if st == "late" else None,
                     "SYSTEM")
                )
            except Exception:
                pass
    conn.commit()


# =============================================================
# FEATURE 1: DEPARTMENT DRILL-DOWN  (pure SQL, no ORM)
# =============================================================

# ── Static taxonomy ──────────────────────────────────────────
# Kept in Python so the frontend can also use the raw data without
# needing a separate config endpoint.
DEPT_META = {
    "CS":    {"name": "Computer Science",       "emoji": "💻", "color": "#4ecba8",
               "courses": {"DS":  {"name": "Data Structures",       "secs": ["A", "B"]},
                           "AI":  {"name": "Artificial Intelligence","secs": ["A"]},
                           "WEB": {"name": "Web Technology",         "secs": ["A", "B"]},
                           "DBMS":{"name": "Database Systems",       "secs": ["A"]}}},
    "ECE":   {"name": "Electronics & Comm",     "emoji": "📡", "color": "#4da6f5",
               "courses": {"DSP": {"name": "Digital Signal Processing","secs": ["A"]},
                           "VLSI":{"name": "VLSI Design",               "secs": ["A", "B"]},
                           "ES":  {"name": "Embedded Systems",          "secs": ["A"]}}},
    "MECH":  {"name": "Mechanical Engineering", "emoji": "⚙️",  "color": "#ffb347",
               "courses": {"TD":  {"name": "Thermodynamics",  "secs": ["A", "B"]},
                           "FM":  {"name": "Fluid Mechanics",  "secs": ["A"]},
                           "CAD": {"name": "CAD/CAM",           "secs": ["A"]}}},
    "CIVIL": {"name": "Civil Engineering",      "emoji": "🏗️",  "color": "#9b87f5",
               "courses": {"SA":  {"name": "Structural Analysis","secs": ["A"]},
                           "RCC": {"name": "RCC Design",          "secs": ["A"]}}},
    "IT":    {"name": "Information Technology", "emoji": "🖧",  "color": "#ff7070",
               "courses": {"PY":  {"name": "Python Programming",    "secs": ["A", "B"]},
                           "NET": {"name": "Computer Networks",      "secs": ["A"]},
                           "SE":  {"name": "Software Engineering",   "secs": ["A"]}}},
}


def _student_att_pct(student_id: str, days: int = 30) -> float:
    """Return attendance % for a student over last `days` days."""
    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    with _conn() as c:
        row = c.execute(
            "SELECT COUNT(DISTINCT date) AS present FROM attendance"
            " WHERE student_id=? AND date>=?",
            (student_id, cutoff)
        ).fetchone()
        present = row["present"] if row else 0
    # count working days (Mon–Fri only)
    working = sum(
        1 for i in range(days)
        if (datetime.now() - timedelta(days=i)).weekday() < 5
    )
    return round(present / max(working, 1) * 100, 1)


def _section_stats(dept: str, course: str, section: str, days: int = 30):
    """Return aggregate stats for a dept/course/section."""
    # Derive students from the students table by roll_number pattern
    # roll_number format stored: "23cs086" → dept hint is "cs"
    # We use the section column directly + cross-reference dept via DEPT_META.
    # Because the demo system stores roll_numbers like "STU_XXXXX", we use
    # section + a deterministic assignment based on student index.
    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    with _conn() as c:
        # All active students in this section
        students = c.execute(
            "SELECT student_id, name FROM students WHERE active=1 AND section=?",
            (section,)
        ).fetchall()

        if not students:
            return {"total": 0, "avg_att": 0, "good": 0, "warn": 0, "poor": 0}

        good = warn = poor = 0
        total_pct = 0.0
        working = max(
            sum(1 for i in range(days)
                if (datetime.now() - timedelta(days=i)).weekday() < 5), 1)

        for s in students:
            row = c.execute(
                "SELECT COUNT(DISTINCT date) AS p FROM attendance"
                " WHERE student_id=? AND date>=?",
                (s["student_id"], cutoff)
            ).fetchone()
            p = row["p"] if row else 0
            pct = round(p / working * 100, 1)
            total_pct += pct
            if pct >= 75:
                good += 1
            elif pct >= 65:
                warn += 1
            else:
                poor += 1

        return {
            "total": len(students),
            "avg_att": round(total_pct / len(students), 1),
            "good": good,
            "warn": warn,
            "poor": poor,
        }


def get_departments_overview() -> list:
    """
    Return list of dept objects each with live attendance stats.
    Used by the Institution Overview level.
    """
    result = []
    for dept_key, meta in DEPT_META.items():
        # Aggregate across all sections
        total_students = avg_att = good = warn = poor = 0
        for course_key, course_meta in meta["courses"].items():
            for sec in course_meta["secs"]:
                s = _section_stats(dept_key, course_key, sec)
                total_students += s["total"]
                avg_att += s["avg_att"] * s["total"]
                good += s["good"]; warn += s["warn"]; poor += s["poor"]

        avg_att = round(avg_att / max(total_students, 1), 1)
        result.append({
            "key":       dept_key,
            "name":      meta["name"],
            "emoji":     meta["emoji"],
            "color":     meta["color"],
            "course_count": len(meta["courses"]),
            "total_students": total_students,
            "avg_att":   avg_att,
            "good":      good,
            "warn":      warn,
            "poor":      poor,
        })
    return result


def get_dept_courses(dept_key: str) -> dict:
    """Return course list + stats for a given dept."""
    meta = DEPT_META.get(dept_key)
    if not meta:
        return {}
    courses = []
    for ck, cm in meta["courses"].items():
        stats = {"total": 0, "avg_att": 0, "good": 0, "warn": 0, "poor": 0}
        for sec in cm["secs"]:
            s = _section_stats(dept_key, ck, sec)
            stats["total"] += s["total"]
            stats["avg_att"] += s["avg_att"] * s["total"]
            stats["good"] += s["good"]; stats["warn"] += s["warn"]
            stats["poor"] += s["poor"]
        stats["avg_att"] = round(stats["avg_att"] / max(stats["total"], 1), 1)
        courses.append({
            "key":     ck,
            "name":    cm["name"],
            "secs":    cm["secs"],
            **stats,
        })
    return {
        "dept_key":   dept_key,
        "dept_name":  meta["name"],
        "dept_color": meta["color"],
        "courses":    courses,
    }


def get_course_sections(dept_key: str, course_key: str) -> dict:
    """Return sections list + stats for a dept/course."""
    meta = DEPT_META.get(dept_key)
    if not meta:
        return {}
    cm = meta["courses"].get(course_key)
    if not cm:
        return {}
    sections = []
    for sec in cm["secs"]:
        s = _section_stats(dept_key, course_key, sec)
        sections.append({"section": sec, **s})
    return {
        "dept_key":    dept_key,
        "course_key":  course_key,
        "course_name": cm["name"],
        "dept_color":  meta["color"],
        "sections":    sections,
    }


def get_section_students(dept_key: str, course_key: str,
                          section: str, days: int = 30) -> dict:
    """Return student list with per-student attendance % for a section."""
    meta = DEPT_META.get(dept_key)
    cm   = (meta or {}).get("courses", {}).get(course_key, {})
    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    working = max(
        sum(1 for i in range(days)
            if (datetime.now() - timedelta(days=i)).weekday() < 5), 1)

    with _conn() as c:
        students = c.execute(
            "SELECT student_id, name, roll_number, mobile, enrolled_on"
            " FROM students WHERE active=1 AND section=? ORDER BY name",
            (section,)
        ).fetchall()

        result = []
        for s in students:
            row = c.execute(
                "SELECT COUNT(DISTINCT date) AS p,"
                " MAX(date) AS last_date"
                " FROM attendance WHERE student_id=? AND date>=?",
                (s["student_id"], cutoff)
            ).fetchone()
            p    = row["p"] if row else 0
            last = (row["last_date"] or "")[:10] if row else ""
            pct  = round(p / working * 100, 1)
            result.append({
                "student_id":  s["student_id"],
                "name":        s["name"] or "?",
                "roll_number": s["roll_number"] or s["student_id"],
                "mobile":      s["mobile"] or "—",
                "enrolled_on": (s["enrolled_on"] or "")[:10],
                "present":     p,
                "total":       working,
                "att_pct":     pct,
                "last_seen":   last,
                "status":      ("good" if pct >= 75
                                else "warn" if pct >= 65 else "poor"),
            })

    return {
        "dept_key":    dept_key,
        "course_key":  course_key,
        "course_name": cm.get("name", course_key),
        "section":     section,
        "dept_color":  (meta or {}).get("color", "#4ecba8"),
        "students":    result,
        "stats": {
            "total":   len(result),
            "avg_att": round(sum(s["att_pct"] for s in result)
                            / max(len(result), 1), 1),
            "good":    sum(1 for s in result if s["status"] == "good"),
            "warn":    sum(1 for s in result if s["status"] == "warn"),
            "poor":    sum(1 for s in result if s["status"] == "poor"),
        },
    }


# =============================================================
# FEATURE 2: FACULTY MANAGEMENT
# =============================================================

def get_all_faculty(dept: str = None, search: str = None,
                    att_date: str = None) -> list:
    """Return faculty list enriched with today's status + 30-day att%."""
    _ensure_faculty_tables()
    target_date = att_date or datetime.now().strftime("%Y-%m-%d")
    cutoff30    = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")

    with _conn() as c:
        sql = "SELECT * FROM faculty WHERE active=1"
        params = []
        if dept:
            sql += " AND dept=?"; params.append(dept)
        if search:
            sql += " AND (name LIKE ? OR fac_id LIKE ?)"; params += [f"%{search}%"] * 2
        sql += " ORDER BY name"
        rows = c.execute(sql, params).fetchall()

        result = []
        for r in rows:
            fac = dict(r)

            # today's / selected date's status
            trow = c.execute(
                "SELECT status, arrival_time FROM faculty_attendance"
                " WHERE fac_id=? AND att_date=?",
                (fac["fac_id"], target_date)
            ).fetchone()
            fac["today_status"]   = trow["status"]        if trow else "not_marked"
            fac["today_arrival"]  = trow["arrival_time"]  if trow else None

            # 30-day attendance %
            arow = c.execute(
                "SELECT COUNT(*) AS total,"
                " SUM(CASE WHEN status IN ('present','late','halfday','od') THEN 1 ELSE 0 END) AS present"
                " FROM faculty_attendance"
                " WHERE fac_id=? AND att_date>=?",
                (fac["fac_id"], cutoff30)
            ).fetchone()
            total   = arow["total"]   if arow else 0
            present = arow["present"] if arow else 0
            working = max(
                sum(1 for i in range(30)
                    if (datetime.now() - timedelta(days=i)).weekday() < 5), 1)
            fac["att_pct"] = round(present / working * 100, 1)

            result.append(fac)
    return result


def get_faculty_detail(fac_id: str, days: int = 30) -> dict:
    """Return single faculty profile + full attendance history."""
    _ensure_faculty_tables()
    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    with _conn() as c:
        fac = c.execute(
            "SELECT * FROM faculty WHERE fac_id=? AND active=1", (fac_id,)
        ).fetchone()
        if not fac:
            return {}
        fac = dict(fac)

        logs = c.execute(
            "SELECT * FROM faculty_attendance"
            " WHERE fac_id=? AND att_date>=? ORDER BY att_date DESC",
            (fac_id, cutoff)
        ).fetchall()
        fac["attendance_log"] = [dict(l) for l in logs]

        # Stats
        total = len(logs)
        present = sum(1 for l in logs
                      if l["status"] in ("present", "late", "halfday", "od"))
        working = max(
            sum(1 for i in range(days)
                if (datetime.now() - timedelta(days=i)).weekday() < 5), 1)
        fac["att_pct"]     = round(present / working * 100, 1)
        fac["total_days"]  = total
        fac["present_days"]= present
        fac["absent_days"] = sum(1 for l in logs if l["status"] == "absent")

        # Monthly breakdown for sparkline (last 6 months)
        monthly = {}
        for l in logs:
            m = l["att_date"][:7]
            monthly.setdefault(m, {"present": 0, "total": 0})
            monthly[m]["total"] += 1
            if l["status"] in ("present", "late", "halfday", "od"):
                monthly[m]["present"] += 1
        fac["monthly"] = [
            {"month": m, **v,
             "pct": round(v["present"] / max(v["total"], 1) * 100, 1)}
            for m, v in sorted(monthly.items())
        ]

    return fac


def get_faculty_analytics() -> dict:
    """
    Aggregate KPIs + chart data for the faculty management page.
    Returns dept-wise bar chart data, status donut data, and KPI strip.
    """
    _ensure_faculty_tables()
    today   = datetime.now().strftime("%Y-%m-%d")
    cutoff  = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
    working = max(
        sum(1 for i in range(30)
            if (datetime.now() - timedelta(days=i)).weekday() < 5), 1)

    with _conn() as c:
        # Overall counts
        total_fac = c.execute(
            "SELECT COUNT(*) FROM faculty WHERE active=1"
        ).fetchone()[0]

        today_rows = c.execute(
            "SELECT status, COUNT(*) AS cnt FROM faculty_attendance"
            " WHERE att_date=? GROUP BY status", (today,)
        ).fetchall()
        status_map = {r["status"]: r["cnt"] for r in today_rows}
        present_today = (status_map.get("present", 0) +
                         status_map.get("late", 0) +
                         status_map.get("halfday", 0) +
                         status_map.get("od", 0))
        absent_today  = status_map.get("absent", 0)
        not_marked    = total_fac - sum(status_map.values())

        # 30-day avg
        avg_row = c.execute(
            "SELECT f.fac_id,"
            " SUM(CASE WHEN a.status IN ('present','late','halfday','od') THEN 1 ELSE 0 END) AS p"
            " FROM faculty f"
            " LEFT JOIN faculty_attendance a"
            "   ON f.fac_id=a.fac_id AND a.att_date>=?"
            " WHERE f.active=1 GROUP BY f.fac_id",
            (cutoff,)
        ).fetchall()
        avg_pct = round(
            sum(r["p"] for r in avg_row) / max(len(avg_row) * working, 1) * 100, 1
        ) if avg_row else 0

        # Dept-wise attendance %
        dept_rows = c.execute(
            "SELECT f.dept,"
            " SUM(CASE WHEN a.status IN ('present','late','halfday','od') THEN 1 ELSE 0 END) AS p,"
            " COUNT(DISTINCT f.fac_id) AS fac_count"
            " FROM faculty f"
            " LEFT JOIN faculty_attendance a"
            "   ON f.fac_id=a.fac_id AND a.att_date>=?"
            " WHERE f.active=1 GROUP BY f.dept ORDER BY f.dept",
            (cutoff,)
        ).fetchall()
        dept_chart = [
            {
                "dept":      r["dept"],
                "fac_count": r["fac_count"],
                "att_pct":   round(r["p"] / max(r["fac_count"] * working, 1) * 100, 1),
            }
            for r in dept_rows
        ]

        # Status donut (today)
        donut = {
            "present": present_today,
            "absent":  absent_today,
            "not_marked": not_marked,
            "late":    status_map.get("late", 0),
            "od":      status_map.get("od", 0),
            "halfday": status_map.get("halfday", 0),
        }

        # Faculty comparison (top + bottom 5 by att%)
        fac_att = c.execute(
            "SELECT f.fac_id, f.name, f.dept,"
            " SUM(CASE WHEN a.status IN ('present','late','halfday','od') THEN 1 ELSE 0 END) AS p"
            " FROM faculty f"
            " LEFT JOIN faculty_attendance a"
            "   ON f.fac_id=a.fac_id AND a.att_date>=?"
            " WHERE f.active=1 GROUP BY f.fac_id ORDER BY p DESC",
            (cutoff,)
        ).fetchall()
        comparison = [
            {"fac_id": r["fac_id"], "name": r["name"], "dept": r["dept"],
             "att_pct": round(r["p"] / max(working, 1) * 100, 1)}
            for r in fac_att
        ]

    return {
        "total_faculty":   total_fac,
        "present_today":   present_today,
        "absent_today":    absent_today,
        "not_marked_today":not_marked,
        "avg_att_30d":     avg_pct,
        "dept_chart":      dept_chart,
        "status_donut":    donut,
        "comparison":      comparison,
    }


def mark_faculty_attendance(fac_id: str, att_date: str, status: str,
                             arrival_time: str = None, reason: str = "",
                             updated_by: str = "ADMIN") -> dict:
    """Insert or replace a faculty attendance log entry."""
    _ensure_faculty_tables()
    with _conn() as c:
        fac = c.execute(
            "SELECT fac_id FROM faculty WHERE fac_id=? AND active=1", (fac_id,)
        ).fetchone()
        if not fac:
            return {"ok": False, "error": "Faculty not found"}
        c.execute(
            "INSERT OR REPLACE INTO faculty_attendance"
            " (fac_id,att_date,status,arrival_time,reason,updated_by)"
            " VALUES (?,?,?,?,?,?)",
            (fac_id, att_date, status, arrival_time, reason, updated_by)
        )
        c.commit()
    return {"ok": True}


def edit_faculty_attendance(log_id: int, status: str,
                             arrival_time: str = None, reason: str = "",
                             updated_by: str = "ADMIN") -> dict:
    """Update a specific faculty_attendance row by its primary key."""
    _ensure_faculty_tables()
    with _conn() as c:
        c.execute(
            "UPDATE faculty_attendance"
            " SET status=?,arrival_time=?,reason=?,updated_by=?"
            " WHERE id=?",
            (status, arrival_time, reason, updated_by, log_id)
        )
        if c.execute("SELECT changes()").fetchone()[0] == 0:
            return {"ok": False, "error": "Log entry not found"}
        c.commit()
    return {"ok": True}


def delete_faculty_attendance(log_id: int) -> dict:
    """Delete a specific faculty_attendance row."""
    _ensure_faculty_tables()
    with _conn() as c:
        c.execute("DELETE FROM faculty_attendance WHERE id=?", (log_id,))
        if c.execute("SELECT changes()").fetchone()[0] == 0:
            return {"ok": False, "error": "Not found"}
        c.commit()
    return {"ok": True}


def create_faculty(fac_id: str, name: str, dept: str,
                   designation: str = "Assistant Professor",
                   email: str = "", mobile: str = "",
                   subjects: list = None) -> dict:
    """Create a new faculty record."""
    _ensure_faculty_tables()
    import json
    subjects_json = json.dumps(subjects or [])
    with _conn() as c:
        try:
            c.execute(
                "INSERT INTO faculty"
                " (fac_id,name,dept,designation,email,mobile,subjects,joined_on)"
                " VALUES (?,?,?,?,?,?,?,?)",
                (fac_id, name, dept, designation, email, mobile,
                 subjects_json, datetime.now().strftime("%Y-%m-%d"))
            )
            c.commit()
            return {"ok": True, "fac_id": fac_id}
        except sqlite3.IntegrityError:
            return {"ok": False, "error": "Faculty ID already exists"}


def export_faculty_csv(dept: str = None) -> str:
    """Return CSV string of all faculty + their 30-day attendance %."""
    rows = get_all_faculty(dept=dept)
    out  = io.StringIO()
    fields = ["fac_id", "name", "dept", "designation", "email",
              "mobile", "att_pct", "today_status"]
    w = csv.DictWriter(out, fieldnames=fields, extrasaction="ignore")
    w.writeheader()
    w.writerows(rows)
    return out.getvalue()


# =============================================================
# ROUTE REGISTRATION  — called from api.py create_app()
# =============================================================

def register_feature_routes(app, get_current_user, teacher_required,
                             admin_required):
    """
    Mount all Feature 1 + Feature 2 API routes onto the FastAPI app.

    Call this at the bottom of create_app(), passing in the dependency
    functions already defined there.
    """
    from fastapi import Depends, Query, HTTPException
    from fastapi.responses import StreamingResponse
    from pydantic import BaseModel
    from typing import Optional

    # ── Pydantic models for faculty feature ─────────────────
    class FacultyAttReq(BaseModel):
        fac_id:       str
        att_date:     str
        status:       str
        arrival_time: Optional[str] = None
        reason:       Optional[str] = ""
        updated_by:   str = "ADMIN"

    class FacultyEditReq(BaseModel):
        status:       str
        arrival_time: Optional[str] = None
        reason:       Optional[str] = ""
        updated_by:   str = "ADMIN"

    class CreateFacultyReq(BaseModel):
        fac_id:      str
        name:        str
        dept:        str
        designation: Optional[str] = "Assistant Professor"
        email:       Optional[str] = ""
        mobile:      Optional[str] = ""
        subjects:    Optional[list] = []

    # ── Ensure tables exist once at startup ─────────────────
    try:
        _ensure_faculty_tables()
    except Exception as e:
        log.error("faculty table init failed: %s", e)

    # ===========================================================
    # FEATURE 1 — DEPARTMENT DRILL-DOWN
    # ===========================================================

    @app.get("/api/departments")
    def api_departments(_: dict = Depends(get_current_user)):
        """
        Institution-level overview: all depts with live attendance stats.
        Also returns the DEPT_META taxonomy so the frontend can build
        dept/course/section dropdowns without extra round-trips.
        """
        try:
            depts = get_departments_overview()
            # Expose taxonomy (course names + sections) for the frontend
            taxonomy = {
                dk: {
                    "name":    dv["name"],
                    "emoji":   dv["emoji"],
                    "color":   dv["color"],
                    "courses": {
                        ck: {"name": cv["name"], "secs": cv["secs"]}
                        for ck, cv in dv["courses"].items()
                    }
                }
                for dk, dv in DEPT_META.items()
            }
            return {"departments": depts, "taxonomy": taxonomy}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @app.get("/api/departments/{dept_key}/courses")
    def api_dept_courses(dept_key: str,
                          _: dict = Depends(get_current_user)):
        """Course-level breakdown for a single department."""
        try:
            data = get_dept_courses(dept_key.upper())
            if not data:
                raise HTTPException(status_code=404,
                                    detail=f"Dept {dept_key} not found")
            return data
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @app.get("/api/departments/{dept_key}/courses/{course_key}/sections")
    def api_course_sections(dept_key: str, course_key: str,
                             _: dict = Depends(get_current_user)):
        """Section-level breakdown for a dept/course."""
        try:
            data = get_course_sections(dept_key.upper(), course_key.upper())
            if not data:
                raise HTTPException(status_code=404, detail="Not found")
            return data
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @app.get("/api/departments/{dept_key}/courses/{course_key}"
             "/sections/{section}/students")
    def api_section_students(dept_key: str, course_key: str,
                              section: str, days: int = 30,
                              _: dict = Depends(get_current_user)):
        """Student list + per-student attendance % for a section."""
        try:
            data = get_section_students(dept_key.upper(),
                                        course_key.upper(),
                                        section.upper(), days)
            return data
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    # ===========================================================
    # FEATURE 2 — FACULTY MANAGEMENT
    # ===========================================================

    @app.get("/api/faculty/analytics/summary")
    def api_faculty_analytics(_: dict = Depends(get_current_user)):
        """KPI strip + chart data for the faculty management page."""
        try:
            return get_faculty_analytics()
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @app.get("/api/faculty")
    def api_faculty_list(dept:     str = Query(None),
                          search:   str = Query(None),
                          att_date: str = Query(None),
                          _: dict = Depends(get_current_user)):
        """Roster of all faculty, filterable by dept/search/date."""
        try:
            return get_all_faculty(dept=dept, search=search,
                                   att_date=att_date)
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @app.post("/api/faculty")
    def api_create_faculty(req: CreateFacultyReq,
                            user: dict = Depends(admin_required)):
        """Create a new faculty record (admin/HOD only)."""
        try:
            res = create_faculty(
                fac_id=req.fac_id.upper(), name=req.name,
                dept=req.dept.upper(), designation=req.designation,
                email=req.email, mobile=req.mobile,
                subjects=req.subjects
            )
            if not res["ok"]:
                raise HTTPException(status_code=409,
                                    detail=res.get("error", "Conflict"))
            return res
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @app.get("/api/faculty/export/csv")
    def api_faculty_export(dept: str = Query(None),
                            _: dict = Depends(get_current_user)):
        """Download faculty attendance CSV."""
        try:
            csv_str = export_faculty_csv(dept=dept)
            date_str = datetime.now().strftime("%Y-%m-%d")
            return StreamingResponse(
                iter([csv_str]),
                media_type="text/csv",
                headers={"Content-Disposition":
                         f"attachment; filename=faculty_att_{date_str}.csv"}
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @app.get("/api/faculty/{fac_id}")
    def api_faculty_detail(fac_id: str, days: int = 30,
                            _: dict = Depends(get_current_user)):
        """Full profile + attendance history for one faculty member."""
        try:
            data = get_faculty_detail(fac_id.upper(), days)
            if not data:
                raise HTTPException(status_code=404,
                                    detail="Faculty not found")
            return data
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @app.post("/api/faculty/attendance")
    def api_mark_faculty_att(req: FacultyAttReq,
                              user: dict = Depends(teacher_required)):
        """Mark or update faculty attendance for a specific date."""
        try:
            res = mark_faculty_attendance(
                fac_id=req.fac_id.upper(), att_date=req.att_date,
                status=req.status, arrival_time=req.arrival_time,
                reason=req.reason, updated_by=req.updated_by
            )
            if not res["ok"]:
                raise HTTPException(status_code=404,
                                    detail=res.get("error"))
            return {"status": "saved", **res}
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @app.put("/api/faculty/{fac_id}/attendance/{log_id}")
    def api_edit_faculty_att(fac_id: str, log_id: int,
                              req: FacultyEditReq,
                              user: dict = Depends(teacher_required)):
        """Edit an existing faculty attendance log entry."""
        try:
            res = edit_faculty_attendance(
                log_id=log_id, status=req.status,
                arrival_time=req.arrival_time, reason=req.reason,
                updated_by=req.updated_by
            )
            if not res["ok"]:
                raise HTTPException(status_code=404,
                                    detail=res.get("error"))
            return {"status": "updated"}
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @app.delete("/api/faculty/{fac_id}/attendance/{log_id}")
    def api_delete_faculty_att(fac_id: str, log_id: int,
                                user: dict = Depends(admin_required)):
        """Delete a faculty attendance log entry (admin only)."""
        try:
            res = delete_faculty_attendance(log_id)
            if not res["ok"]:
                raise HTTPException(status_code=404,
                                    detail=res.get("error"))
            return {"status": "deleted"}
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    log.info("Feature routes (departments + faculty) registered.")