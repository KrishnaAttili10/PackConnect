
from flask import Flask, jsonify, request, session
from flask_cors import CORS
from flask.json.provider import DefaultJSONProvider
from psycopg import OperationalError
from psycopg.errors import UniqueViolation
import re
from werkzeug.security import generate_password_hash, check_password_hash
from pathlib import Path
from messaging import create_messaging_blueprint, initialize_messaging
from database import connect_database
from identity import registered_student_sql, session_student_id
from availability import availability_payload, workload_join, availability_columns, availability_status_sql

import os
import secrets
from datetime import date, datetime, timedelta
from dotenv import load_dotenv
from supabase import create_client
from supabase.lib.client_options import SyncClientOptions
from supabase_auth.errors import AuthApiError, AuthRetryableError
from httpx import HTTPError

load_dotenv(Path(__file__).parent / ".env")

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SECRET_KEY = os.getenv("SUPABASE_SECRET_KEY")

if (SUPABASE_SECRET_KEY and not SUPABASE_URL) or (
    SUPABASE_URL and not (SUPABASE_SECRET_KEY or os.getenv("SUPABASE_PUBLISHABLE_KEY")
                         or os.getenv("SUPABASE_ANON_KEY"))
):
    raise RuntimeError("Set SUPABASE_URL and a Supabase key in backend/.env")

supabase = (
    create_client(SUPABASE_URL, SUPABASE_SECRET_KEY)
    if SUPABASE_URL and SUPABASE_SECRET_KEY
    else None
)

class PortalJSONProvider(DefaultJSONProvider):
    @staticmethod
    def default(value):
        if isinstance(value, date):
            return value.isoformat()
        return DefaultJSONProvider.default(value)


app = Flask(__name__)
app.json = PortalJSONProvider(app)
app.config.update(
    SECRET_KEY=os.getenv("FLASK_SECRET_KEY") or secrets.token_hex(32),
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.getenv("COOKIE_SECURE") == "true",
    PERMANENT_SESSION_LIFETIME=timedelta(hours=8),
)
CORS(app)

app.config["SUPABASE_DB_URL"] = os.getenv("SUPABASE_DB_URL")


def get_db():
    return connect_database(app.config.get("SUPABASE_DB_URL"), app.config.get("TEST_DB_SCHEMA"))


app.register_blueprint(create_messaging_blueprint(get_db))


def normalize_courses(courses):
    if not isinstance(courses, list) or any(not isinstance(course, str) for course in courses):
        raise ValueError("Courses must be a list of course-code strings.")

    normalized = []
    seen = set()

    for course in courses:
        course_code = course.strip().upper()
        if course_code and course_code not in seen:
            normalized.append(course_code)
            seen.add(course_code)

    return normalized


def profile_payload(data):
    payload = {}
    for field in ("name", "program", "year", "bio", "interests", "skills", "advice_topics"):
        value = data.get(field, "")
        if not isinstance(value, str):
            raise ValueError(f"{field.replace('_', ' ').capitalize()} must be text.")
        payload[field] = value.strip()
    willing = data.get("willing_to_advise", True)
    if not isinstance(willing, bool):
        raise ValueError("Willing to advise must be true or false.")
    payload["willing_to_advise"] = willing
    payload.update(availability_payload(data))
    return payload


def replace_courses(db, table_name, student_id, courses):
    db.execute(f"DELETE FROM {table_name} WHERE student_id = %s", (student_id,))

    for course in courses:
        db.execute(
            f"""
            INSERT INTO {table_name}
            (student_id, course_code)
            VALUES (%s, %s)
            """,
            (student_id, course),
        )


def fetch_student(db, student_id):
    student = db.execute(f"""
        SELECT s.id, s.name, s.program, s.year, s.bio, s.interests, s.skills,
               s.advice_topics, s.willing_to_advise, {availability_columns()}
        FROM students s {workload_join()}
        WHERE s.id = %s
    """, (student_id,)).fetchone()

    if student is None:
        return None

    completed_courses = db.execute("""
        SELECT course_code
        FROM completed_courses
        WHERE student_id = %s
        ORDER BY course_code
    """, (student_id,)).fetchall()

    current_courses = db.execute("""
        SELECT course_code
        FROM current_courses
        WHERE student_id = %s
        ORDER BY course_code
    """, (student_id,)).fetchall()

    profile = dict(student)
    profile["can_receive_requests"] = bool(db.execute(
        f"SELECT s.id FROM students s WHERE s.id = %s AND {registered_student_sql()}",
        (student_id,),
    ).fetchone())
    profile["completed_courses"] = [
        row["course_code"] for row in completed_courses
    ]
    profile["current_courses"] = [
        row["course_code"] for row in current_courses
    ]
    profile["willing_to_advise"] = bool(profile["willing_to_advise"])

    return profile


def initialize_database():
    # Migrations are explicit. Startup never creates or falls back to a local DB.
    with get_db() as db:
        db.execute("SELECT student_id, email, password_hash FROM accounts LIMIT 0")
        initialize_messaging(db)


@app.route("/api/health")
def health():
    with get_db() as db:
        db.execute("SELECT id FROM accounts LIMIT 0")
    return jsonify({"status": "ok"})


@app.errorhandler(OperationalError)
def database_unavailable(error):
    return jsonify({"error": "Database unavailable. Please try again shortly."}), 503


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
    email = email.strip().lower()
    with get_db() as db:
        account = db.execute(
            "SELECT student_id, password_hash FROM accounts WHERE lower(email) = %s",
            (email,),
        ).fetchone()
    auth_user_id = None
    if account:
        if not check_password_hash(account["password_hash"], password):
            return jsonify({"error": "Email or password is incorrect."}), 401
        student_id = account["student_id"]
    else:
        # Keep user tokens out of the shared admin client and Flask session.
        key = (os.getenv("SUPABASE_PUBLISHABLE_KEY") or os.getenv("SUPABASE_ANON_KEY")
               or SUPABASE_SECRET_KEY)
        if not SUPABASE_URL or not key:
            check_password_hash(DUMMY_PASSWORD_HASH, password)
            return jsonify({"error": "Email or password is incorrect."}), 401
        auth_client = None
        try:
            auth_client = create_client(SUPABASE_URL, key, options=SyncClientOptions(
                auto_refresh_token=False, persist_session=False,
            ))
            result = auth_client.auth.sign_in_with_password({"email": email, "password": password})
        except AuthApiError:
            return jsonify({"error": "Email or password is incorrect."}), 401
        except (HTTPError, AuthRetryableError):
            return jsonify({"error": "Sign-in service is unavailable. Please try again."}), 503
        finally:
            if auth_client is not None:
                auth_client.auth.close()
        auth_user = result.user
        if (not auth_user or not auth_user.email_confirmed_at
                or not auth_user.email or auth_user.email.lower() != email):
            return jsonify({"error": "Email or password is incorrect."}), 401
        auth_user_id = str(auth_user.id)
        # Use the verified immutable ID; names and email alone never link profiles.
        with get_db() as db:
            linked = db.execute("""
                SELECT s.id FROM students s JOIN auth.users u ON u.id = s.auth_user_id
                WHERE u.id = %s AND u.email_confirmed_at IS NOT NULL
            """, (auth_user_id,)).fetchone()
        if not linked:
            return jsonify({"error": "This account has no linked student profile. Contact the project team."}), 403
        student_id = linked["id"]
    with get_db() as db:
        student = fetch_student(db, student_id)
    if student is None:
        return jsonify({"error": "This account has no student profile."}), 401
    session.clear()
    session.permanent = True
    session["student_id"] = student["id"]
    if auth_user_id:
        session["auth_user_id"] = auth_user_id
    return jsonify({"student": student})


@app.route("/api/auth/me")
def current_user():
    with get_db() as db:
        student = fetch_student(db, session_student_id(db, session))
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
    try:
        advising = {"max_open_requests": 5, "pause_until": None, **availability_payload(data)}
    except ValueError as error:
        return jsonify({"error": str(error)}), 400
    password_hash = generate_password_hash(password)
    try:
        with get_db() as db:
            if db.execute("SELECT 1 FROM auth.users WHERE lower(email) = %s", (email,)).fetchone():
                return jsonify({"error": "An account with this email already exists."}), 409
            cursor = db.execute("""
                INSERT INTO students (name, program, year, bio, interests, willing_to_advise, max_open_requests, pause_until)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING id
            """, (fields["name"], fields["program"], fields["year"],
                  fields["bio"], fields["interests"], willing, advising["max_open_requests"], advising["pause_until"]))
            student_id = cursor.fetchone()["id"]
            db.execute("""
                INSERT INTO accounts (student_id, email, password_hash) VALUES (%s, %s, %s)
            """, (student_id, email, password_hash))
            db.cursor().executemany("""
                INSERT INTO completed_courses (student_id, course_code) VALUES (%s, %s)
            """, [(student_id, course) for course in courses])
    except UniqueViolation:
        return jsonify({"error": "An account with this email already exists."}), 409

    return jsonify({"student": {"id": student_id, **{key: value for key, value in fields.items()
                                                    if key != "email"},
                                "willing_to_advise": willing, "completed_courses": courses, **advising}}), 201


@app.route("/api/students", methods=["POST"])
def create_student():
    return jsonify({"error": "Create your profile through account registration."}), 410


def course_key(value):
    """Ignore spacing and hyphens consistently for discovery and matching."""
    return re.sub(r"[\s-]+", "", value).upper()


@app.route("/api/courses")
def suggest_courses():
    query = course_key(request.args.get("q", ""))
    if not query or len(query) > 30:
        return jsonify({"courses": []})
    with get_db() as db:
        rows = db.execute(f"""
            SELECT DISTINCT regexp_replace(UPPER(c.course_code), '[[:space:]-]+', '', 'g') AS code
            FROM completed_courses c
            JOIN students s ON s.id = c.student_id
            WHERE {registered_student_sql()}
              AND starts_with(regexp_replace(UPPER(c.course_code), '[[:space:]-]+', '', 'g'), %s)
            ORDER BY code LIMIT 10
        """, (query,)).fetchall()
    return jsonify({"courses": [re.sub(r"^([A-Z]+)(\d)", r"\1 \2", row["code"]) for row in rows]})


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

    # Include both local accounts and confirmed Supabase registrations.
    conditions = [registered_student_sql()]
    parameters = []

    if course:
        conditions.append("""
            EXISTS (
                SELECT 1
                FROM completed_courses c
                WHERE c.student_id = s.id
                  AND regexp_replace(UPPER(c.course_code), '[[:space:]-]+', '', 'g') = %s
            )
        """)
        parameters.append(course_key(course))

    if available != "false":
        conditions.append(f"({availability_status_sql()}) = 'available'")

    for column, value in (
        ("s.program", program),
        ("s.year", year),
        ("s.skills", skills),
        ("s.advice_topics", advice_topics),
    ):
        if value:
            conditions.append(f"LOWER(COALESCE({column}, '')) LIKE %s")
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
                s.willing_to_advise, {availability_columns()}
            FROM students s {workload_join()}
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
    with get_db() as db:
        owner_id = session_student_id(db, session)
    if owner_id is None:
        return jsonify({"error": "Sign in to edit your profile."}), 401
    if owner_id != student_id:
        return jsonify({"error": "You can only edit your own profile."}), 403
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "Send a JSON object with your profile details."}), 400
    try:
        payload = profile_payload(data)
        completed_courses = normalize_courses(data.get("completed_courses", []))
        current_courses = normalize_courses(data.get("current_courses", []))
    except ValueError as error:
        return jsonify({"error": str(error)}), 400

    if not payload["name"] or not payload["program"] or not payload["year"]:
        return jsonify({
            "error": "Name, program, and year are required."
        }), 400

    with get_db() as db:
        existing_student = db.execute("""
            SELECT id, max_open_requests, pause_until
            FROM students
            WHERE id = %s FOR NO KEY UPDATE
        """, (student_id,)).fetchone()

        if existing_student is None:
            return jsonify({"error": "Student not found"}), 404

        db.execute("""
            UPDATE students
            SET name = %s,
                program = %s,
                year = %s,
                bio = %s,
                interests = %s,
                skills = %s,
                advice_topics = %s,
                willing_to_advise = %s,
                max_open_requests = %s,
                pause_until = %s
            WHERE id = %s
        """, (
            payload["name"],
            payload["program"],
            payload["year"],
            payload["bio"],
            payload["interests"],
            payload["skills"],
            payload["advice_topics"],
            payload["willing_to_advise"],
            payload.get("max_open_requests", existing_student["max_open_requests"]),
            payload.get("pause_until", existing_student["pause_until"]),
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
