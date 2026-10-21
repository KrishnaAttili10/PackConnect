
from flask import Flask, jsonify, request, session
from flask_cors import CORS
import sqlite3
import re
from werkzeug.security import generate_password_hash, check_password_hash
from pathlib import Path
from contextlib import contextmanager
from messaging import create_messaging_blueprint, initialize_messaging

import os
import secrets
from datetime import timedelta
from dotenv import load_dotenv
from supabase import create_client

load_dotenv(Path(__file__).parent / ".env")

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SECRET_KEY = os.getenv("SUPABASE_SECRET_KEY")

if bool(SUPABASE_URL) != bool(SUPABASE_SECRET_KEY):
    raise RuntimeError("Set both SUPABASE_URL and SUPABASE_SECRET_KEY in backend/.env")

supabase = (
    create_client(SUPABASE_URL, SUPABASE_SECRET_KEY)
    if SUPABASE_URL and SUPABASE_SECRET_KEY
    else None
)

app = Flask(__name__)
app.config.update(
    SECRET_KEY=os.getenv("FLASK_SECRET_KEY") or secrets.token_hex(32),
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.getenv("COOKIE_SECURE") == "true",
    PERMANENT_SESSION_LIFETIME=timedelta(hours=8),
)
CORS(app)

DB_PATH = Path(__file__).parent / "peer_advice.db"


@contextmanager
def get_db():
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    try:
        with connection:
            yield connection
    finally:
        connection.close()


app.register_blueprint(create_messaging_blueprint(get_db))


def ensure_student_columns(db):
    existing_columns = {
        row["name"] for row in db.execute("PRAGMA table_info(students)")
    }

    for column in ("skills", "advice_topics"):
        if column not in existing_columns:
            db.execute(f"ALTER TABLE students ADD COLUMN {column} TEXT")


def normalize_courses(courses):
    if not isinstance(courses, list):
        return []

    normalized = []
    seen = set()

    for course in courses:
        course_code = str(course).strip().upper()
        if course_code and course_code not in seen:
            normalized.append(course_code)
            seen.add(course_code)

    return normalized


def profile_payload(data):
    return {
        "name": str(data.get("name", "")).strip(),
        "program": str(data.get("program", "")).strip(),
        "year": str(data.get("year", "")).strip(),
        "bio": str(data.get("bio", "")).strip(),
        "interests": str(data.get("interests", "")).strip(),
        "skills": str(data.get("skills", "")).strip(),
        "advice_topics": str(data.get("advice_topics", "")).strip(),
        "willing_to_advise": 1
        if data.get("willing_to_advise", True)
        else 0,
    }


def replace_courses(db, table_name, student_id, courses):
    db.execute(f"DELETE FROM {table_name} WHERE student_id = ?", (student_id,))

    for course in courses:
        db.execute(
            f"""
            INSERT INTO {table_name}
            (student_id, course_code)
            VALUES (?, ?)
            """,
            (student_id, course),
        )


def fetch_student(db, student_id):
    student = db.execute("""
        SELECT *
        FROM students
        WHERE id = ?
    """, (student_id,)).fetchone()

    if student is None:
        return None

    completed_courses = db.execute("""
        SELECT course_code
        FROM completed_courses
        WHERE student_id = ?
        ORDER BY course_code
    """, (student_id,)).fetchall()

    current_courses = db.execute("""
        SELECT course_code
        FROM current_courses
        WHERE student_id = ?
        ORDER BY course_code
    """, (student_id,)).fetchall()

    profile = dict(student)
    profile["can_receive_requests"] = bool(db.execute("SELECT 1 FROM accounts WHERE student_id = ?", (student_id,)).fetchone())
    profile["completed_courses"] = [
        row["course_code"] for row in completed_courses
    ]
    profile["current_courses"] = [
        row["course_code"] for row in current_courses
    ]
    profile["willing_to_advise"] = bool(profile["willing_to_advise"])

    return profile


def initialize_database():
    with get_db() as db:
        db.execute("""
            CREATE TABLE IF NOT EXISTS students (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                program TEXT NOT NULL,
                year TEXT NOT NULL,
                bio TEXT,
                interests TEXT,
                willing_to_advise INTEGER NOT NULL DEFAULT 1
            )
        """)

        ensure_student_columns(db)

        db.execute("""
            CREATE TABLE IF NOT EXISTS accounts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id INTEGER NOT NULL UNIQUE,
                email TEXT NOT NULL UNIQUE COLLATE NOCASE,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (student_id) REFERENCES students(id)
            )
        """)

        db.execute("""
            CREATE TABLE IF NOT EXISTS completed_courses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id INTEGER NOT NULL,
                course_code TEXT NOT NULL,
                FOREIGN KEY (student_id) REFERENCES students(id)
            )
        """)

        db.execute("""
            CREATE TABLE IF NOT EXISTS current_courses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id INTEGER NOT NULL,
                course_code TEXT NOT NULL,
                FOREIGN KEY (student_id) REFERENCES students(id)
            )
        """)

        db.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                recipient_id INTEGER NOT NULL,
                sender_name TEXT NOT NULL,
                body TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (recipient_id) REFERENCES students(id)
            )
        """)

        initialize_messaging(db)

        count = db.execute(
            "SELECT COUNT(*) FROM students"
        ).fetchone()[0]

        if count == 0:
            students = [
                (
                    "Alex Morgan",
                    "MS Computer Science",
                    "Second Year",
                    "I enjoy helping students prepare for software "
                    "engineering courses and team projects.",
                    "Software Engineering, Web Development",
                    1,
                    ["CSC 510", "CSC 540"],
                ),
                (
                    "Jordan Lee",
                    "MS Computer Science",
                    "First Year",
                    "Happy to share my experience with course "
                    "assignments and study strategies.",
                    "AI, Databases",
                    1,
                    ["CSC 510", "CSC 515"],
                ),
                (
                    "Taylor Kim",
                    "MS Computer Science",
                    "Second Year",
                    "Interested in helping peers navigate "
                    "graduate-level computer science courses.",
                    "Machine Learning, Databases",
                    1,
                    ["CSC 540", "CSC 515"],
                ),
                (
                    "Sam Patel",
                    "MS Computer Science",
                    "Second Year",
                    "I can share tips about software engineering "
                    "projects and working in teams.",
                    "Software Engineering, Cloud Computing",
                    1,
                    ["CSC 510"],
                ),
            ]

            for student in students:
                name, program, year, bio, interests, willing, courses = student

                cursor = db.execute("""
                    INSERT INTO students
                    (name, program, year, bio, interests, skills,
                     advice_topics, willing_to_advise)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    name,
                    program,
                    year,
                    bio,
                    interests,
                    "",
                    "Workload, Projects, Course Prep",
                    willing,
                ))

                student_id = cursor.lastrowid

                for course in courses:
                    db.execute("""
                        INSERT INTO completed_courses
                        (student_id, course_code)
                        VALUES (?, ?)
                    """, (student_id, course))

        db.commit()


@app.route("/api/health")
def health():
    return jsonify({"status": "ok"})


DUMMY_PASSWORD_HASH = generate_password_hash(secrets.token_hex(32))


@app.route("/api/auth/login", methods=["POST"])
def login():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "Send an email and password."}), 400
    email, password = data.get("email"), data.get("password")
    if (not isinstance(email, str) or not isinstance(password, str)
            or not email.strip() or not password or len(email) > 254
            or len(password) > 128):
        return jsonify({"error": "Enter your email and password."}), 400
    with get_db() as db:
        account = db.execute(
            "SELECT student_id, password_hash FROM accounts WHERE email = ?",
            (email.strip().lower(),),
        ).fetchone()
        valid = check_password_hash(
            account["password_hash"] if account else DUMMY_PASSWORD_HASH, password
        )
        if not account or not valid:
            return jsonify({"error": "Email or password is incorrect."}), 401
        student = fetch_student(db, account["student_id"])
    if student is None:
        return jsonify({"error": "This account has no student profile."}), 401
    session.clear()
    session.permanent = True
    session["student_id"] = student["id"]
    return jsonify({"student": student})


@app.route("/api/auth/me")
def current_user():
    with get_db() as db:
        student = fetch_student(db, session.get("student_id"))
    if student is None:
        session.clear()
        return jsonify({"error": "Sign in to continue."}), 401
    return jsonify({"student": student})


@app.route("/api/auth/logout", methods=["POST"])
def logout():
    session.clear()
    return jsonify({"status": "ok"})


@app.route("/api/auth/register", methods=["POST"])
def register():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "Send a JSON object with your registration details."}), 400

    fields = {}
    for field, limit in [("name", 100), ("email", 254), ("program", 100),
                         ("year", 50), ("bio", 2000), ("interests", 500)]:
        value = data.get(field, "")
        if not isinstance(value, str) or len(value.strip()) > limit:
            return jsonify({"error": f"{field.capitalize()} must be text of at most {limit} characters."}), 400
        fields[field] = value.strip()
    if not all(fields[field] for field in ("name", "email", "program", "year")):
        return jsonify({"error": "Name, email, program, and year are required."}), 400
    email = fields["email"].lower()
    if not re.fullmatch(r"[^\s@]+@[^\s@.]+(?:\.[^\s@.]+)+", email):
        return jsonify({"error": "Please enter a valid email address."}), 400
    password = data.get("password")
    if not isinstance(password, str) or not 12 <= len(password) <= 128:
        return jsonify({"error": "Password must be between 12 and 128 characters."}), 400
    willing = data.get("willing_to_advise", False)
    if not isinstance(willing, bool):
        return jsonify({"error": "Willing to advise must be true or false."}), 400
    courses = data.get("completed_courses", [])
    if (not isinstance(courses, list) or len(courses) > 50
            or any(not isinstance(course, str) or not course.strip()
                   or len(course.strip()) > 30 for course in courses)):
        return jsonify({"error": "Provide up to 50 completed course codes, each at most 30 characters."}), 400
    courses = sorted({course.strip().upper() for course in courses})
    password_hash = generate_password_hash(password)
    try:
        with get_db() as db:
            cursor = db.execute("""
                INSERT INTO students (name, program, year, bio, interests, willing_to_advise)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (fields["name"], fields["program"], fields["year"],
                  fields["bio"], fields["interests"], int(willing)))
            student_id = cursor.lastrowid
            db.execute("""
                INSERT INTO accounts (student_id, email, password_hash) VALUES (?, ?, ?)
            """, (student_id, email, password_hash))
            db.executemany("""
                INSERT INTO completed_courses (student_id, course_code) VALUES (?, ?)
            """, [(student_id, course) for course in courses])
    except sqlite3.IntegrityError:
        return jsonify({"error": "An account with this email already exists."}), 409

    return jsonify({"student": {"id": student_id, **{key: value for key, value in fields.items()
                                                    if key != "email"},
                                "willing_to_advise": willing, "completed_courses": courses}}), 201


@app.route("/api/students", methods=["POST"])
def create_student():
    data = request.get_json(silent=True) or {}
    payload = profile_payload(data)

    if not payload["name"] or not payload["program"] or not payload["year"]:
        return jsonify({
            "error": "Name, program, and year are required."
        }), 400

    completed_courses = normalize_courses(data.get("completed_courses", []))
    current_courses = normalize_courses(data.get("current_courses", []))

    with get_db() as db:
        cursor = db.execute("""
            INSERT INTO students
            (name, program, year, bio, interests, skills, advice_topics,
             willing_to_advise)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            payload["name"],
            payload["program"],
            payload["year"],
            payload["bio"],
            payload["interests"],
            payload["skills"],
            payload["advice_topics"],
            payload["willing_to_advise"],
        ))

        student_id = cursor.lastrowid
        replace_courses(db, "completed_courses", student_id, completed_courses)
        replace_courses(db, "current_courses", student_id, current_courses)
        student = fetch_student(db, student_id)

    return jsonify({"student": student}), 201


@app.route("/api/students/search")
def search_students():
    course = request.args.get("course", "").strip().upper()
    program = request.args.get("program", "").strip()
    year = request.args.get("year", "").strip()
    skills = request.args.get("skills", "").strip()
    advice_topics = request.args.get("advice_topics", "").strip()
    available = request.args.get("available", "true").strip().lower()

    if not any((course, program, year, skills, advice_topics)):
        return jsonify({"students": []})

    conditions = []
    parameters = []

    if course:
        conditions.append("""
            EXISTS (
                SELECT 1
                FROM completed_courses c
                WHERE c.student_id = s.id
                  AND UPPER(c.course_code) = ?
            )
        """)
        parameters.append(course)

    if available != "false":
        conditions.append("s.willing_to_advise = 1")

    for column, value in (
        ("s.program", program),
        ("s.year", year),
        ("s.skills", skills),
        ("s.advice_topics", advice_topics),
    ):
        if value:
            conditions.append(f"LOWER(COALESCE({column}, '')) LIKE ?")
            parameters.append(f"%{value.lower()}%")

    where_clause = " AND ".join(conditions) if conditions else "1 = 1"

    with get_db() as db:
        rows = db.execute(f"""
            SELECT DISTINCT
                s.id,
                s.name,
                s.program,
                s.year,
                s.skills,
                s.advice_topics,
                s.willing_to_advise
            FROM students s
            WHERE {where_clause}
            ORDER BY s.name
        """, parameters).fetchall()

    return jsonify({
        "students": [dict(row) for row in rows]
    })


@app.route("/api/students/<int:student_id>")
def student_profile(student_id):
    with get_db() as db:
        student = fetch_student(db, student_id)

        if student is None:
            return jsonify({"error": "Student not found"}), 404

    return jsonify({"student": student})


@app.route("/api/students/<int:student_id>", methods=["PUT"])
def update_student(student_id):
    owner_id = session.get("student_id")
    if owner_id is None:
        return jsonify({"error": "Sign in to edit your profile."}), 401
    if owner_id != student_id:
        return jsonify({"error": "You can only edit your own profile."}), 403
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "Send a JSON object with your profile details."}), 400
    payload = profile_payload(data)

    if not payload["name"] or not payload["program"] or not payload["year"]:
        return jsonify({
            "error": "Name, program, and year are required."
        }), 400

    completed_courses = normalize_courses(data.get("completed_courses", []))
    current_courses = normalize_courses(data.get("current_courses", []))

    with get_db() as db:
        existing_student = db.execute("""
            SELECT id
            FROM students
            WHERE id = ?
        """, (student_id,)).fetchone()

        if existing_student is None:
            return jsonify({"error": "Student not found"}), 404

        db.execute("""
            UPDATE students
            SET name = ?,
                program = ?,
                year = ?,
                bio = ?,
                interests = ?,
                skills = ?,
                advice_topics = ?,
                willing_to_advise = ?
            WHERE id = ?
        """, (
            payload["name"],
            payload["program"],
            payload["year"],
            payload["bio"],
            payload["interests"],
            payload["skills"],
            payload["advice_topics"],
            payload["willing_to_advise"],
            student_id,
        ))

        replace_courses(db, "completed_courses", student_id, completed_courses)
        replace_courses(db, "current_courses", student_id, current_courses)
        student = fetch_student(db, student_id)

    return jsonify({"student": student})


@app.route("/api/students/<int:student_id>/messages", methods=["POST"])
def send_message(student_id):
    return jsonify({"error": "Direct messages have moved to accepted-request conversations. Open Requests to chat."}), 410


if __name__ == "__main__":
    initialize_database()
    app.run(debug=True, port=5000)
