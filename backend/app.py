"""PackConnect Flask API backed by Supabase only; no SQLite or local password storage."""
from datetime import timedelta
from pathlib import Path
import os
import re
import secrets

from dotenv import load_dotenv
from flask import Flask, jsonify, request, session
from flask_cors import CORS
from supabase import create_client
try:
    from .messaging import create_messaging_blueprint
except ImportError:
    from messaging import create_messaging_blueprint

load_dotenv(Path(__file__).parent / ".env")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SECRET_KEY = os.getenv("SUPABASE_SECRET_KEY")
SUPABASE_PUBLISHABLE_KEY = os.getenv("SUPABASE_PUBLISHABLE_KEY")
supabase = create_client(SUPABASE_URL, SUPABASE_SECRET_KEY) if SUPABASE_URL and SUPABASE_SECRET_KEY else None
auth_supabase = create_client(SUPABASE_URL, SUPABASE_PUBLISHABLE_KEY) if SUPABASE_URL and SUPABASE_PUBLISHABLE_KEY else None

app = Flask(__name__)
app.config.update(
    SECRET_KEY=os.getenv("FLASK_SECRET_KEY") or secrets.token_hex(32),
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.getenv("COOKIE_SECURE", "").lower() == "true",
    PERMANENT_SESSION_LIFETIME=timedelta(hours=8),
)
CORS(app)
app.register_blueprint(create_messaging_blueprint(supabase))


def error(message, status=400):
    return jsonify({"error": message}), status


def normalize_courses(courses):
    if not isinstance(courses, list):
        return []
    result, seen = [], set()
    for course in courses:
        code = str(course).strip().upper()
        if code and code not in seen:
            result.append(code)
            seen.add(code)
    return result


def profile_payload(data):
    return {
        "name": str(data.get("name", "")).strip(),
        "program": str(data.get("program", "")).strip(),
        "year": str(data.get("year", "")).strip(),
        "bio": str(data.get("bio", "")).strip(),
        "interests": str(data.get("interests", "")).strip(),
        "skills": str(data.get("skills", "")).strip(),
        "advice_topics": str(data.get("advice_topics", "")).strip(),
        "willing_to_advise": bool(data.get("willing_to_advise", True)),
    }


def fetch_student(student_id, expected_auth_user_id=None):
    if supabase is None or student_id is None:
        return None
    rows = supabase.table("students").select("*").eq("id", student_id).limit(1).execute().data or []
    if not rows:
        return None
    raw = rows[0]
    if expected_auth_user_id is not None and raw.get("auth_user_id") != expected_auth_user_id:
        return None
    completed = supabase.table("completed_courses").select("course_code").eq("student_id", student_id).order("course_code").execute().data or []
    current = supabase.table("current_courses").select("course_code").eq("student_id", student_id).order("course_code").execute().data or []
    profile = dict(raw)
    profile.pop("auth_user_id", None)
    profile["can_receive_requests"] = bool(raw.get("auth_user_id"))
    profile["completed_courses"] = [r["course_code"] for r in completed]
    profile["current_courses"] = [r["course_code"] for r in current]
    profile["willing_to_advise"] = bool(profile.get("willing_to_advise", False))
    return profile


def replace_courses(table_name, student_id, courses):
    if table_name not in {"completed_courses", "current_courses"}:
        raise ValueError("Unsupported course table")
    supabase.table(table_name).delete().eq("student_id", student_id).execute()
    rows = [{"student_id": student_id, "course_code": c} for c in normalize_courses(courses)]
    if rows:
        supabase.table(table_name).insert(rows).execute()


def session_student():
    if supabase is None or session.get("student_id") is None or not session.get("auth_user_id"):
        return None
    return fetch_student(session["student_id"], expected_auth_user_id=session["auth_user_id"])


@app.route("/api/health")
def health():
    return jsonify({"status": "ok", "database": "supabase" if supabase else "not_configured"})


@app.route("/api/auth/login", methods=["POST"])
def login():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return error("Send an email and password.")
    email, password = data.get("email"), data.get("password")
    if not isinstance(email, str) or not isinstance(password, str) or not email.strip() or not password or len(email) > 254 or len(password) > 128:
        return error("Enter your email and password.")
    if auth_supabase is None or supabase is None:
        return error("Authentication is not configured. Check the backend environment.", 503)
    try:
        result = auth_supabase.auth.sign_in_with_password({"email": email.strip().lower(), "password": password})
        user = result.user
        if user is None:
            return error("Email or password is incorrect.", 401)
        rows = supabase.table("students").select("id").eq("auth_user_id", str(user.id)).limit(1).execute().data or []
        if not rows:
            return error("This account has no student profile.", 401)
        student = fetch_student(rows[0]["id"], expected_auth_user_id=str(user.id))
        if student is None:
            return error("This account has no student profile.", 401)
        session.clear()
        session.permanent = True
        session["student_id"] = student["id"]
        session["auth_user_id"] = str(user.id)
        return jsonify({"student": student})
    except Exception:
        return error("Email or password is incorrect.", 401)


@app.route("/api/auth/me")
def current_user():
    student = session_student()
    if student is None:
        session.clear()
        return error("Sign in to continue.", 401)
    return jsonify({"student": student})


@app.route("/api/auth/logout", methods=["POST"])
def logout():
    session.clear()
    return jsonify({"status": "ok"})


@app.route("/api/auth/register", methods=["POST"])
def register():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return error("Send a JSON object with your registration details.")
    if auth_supabase is None or supabase is None:
        return error("Authentication is not configured. Check the backend environment.", 503)
    fields = {}
    for field, limit in [("name", 100), ("email", 254), ("program", 100), ("year", 50), ("bio", 2000), ("interests", 500)]:
        value = data.get(field, "")
        if not isinstance(value, str) or len(value.strip()) > limit:
            return error(f"{field.capitalize()} must be text of at most {limit} characters.")
        fields[field] = value.strip()
    if not all(fields[k] for k in ("name", "email", "program", "year")):
        return error("Name, email, program, and year are required.")
    email = fields["email"].lower()
    if not re.fullmatch(r"[^\s@]+@[^\s@.]+(?:\.[^\s@.]+)+", email):
        return error("Please enter a valid email address.")
    password = data.get("password")
    if not isinstance(password, str) or not 12 <= len(password) <= 128:
        return error("Password must be between 12 and 128 characters.")
    willing = data.get("willing_to_advise", False)
    if not isinstance(willing, bool):
        return error("Willing to advise must be true or false.")
    courses = data.get("completed_courses", [])
    if not isinstance(courses, list) or len(courses) > 50 or any(not isinstance(c, str) or not c.strip() or len(c.strip()) > 30 for c in courses):
        return error("Provide up to 50 completed course codes, each at most 30 characters.")
    courses = sorted(set(normalize_courses(courses)))
    user_id = profile_id = None
    try:
        auth_result = auth_supabase.auth.sign_up({"email": email, "password": password, "options": {"data": {"name": fields["name"]}}})
        user = auth_result.user
        if user is None:
            return error("Unable to create the account. Please try again.", 400)
        user_id = str(user.id)
        identities = getattr(user, "identities", None)
        if identities is not None and len(identities) == 0:
            return error("An account with this email already exists.", 409)
        inserted = supabase.table("students").insert({
            "auth_user_id": user_id, "name": fields["name"], "program": fields["program"],
            "year": fields["year"], "bio": fields["bio"], "interests": fields["interests"],
            "skills": "", "advice_topics": "", "willing_to_advise": willing,
        }).execute().data or []
        if not inserted:
            raise RuntimeError("Supabase did not return the created profile")
        profile_id = inserted[0]["id"]
        if courses:
            supabase.table("completed_courses").insert([{"student_id": profile_id, "course_code": c} for c in courses]).execute()
        student = fetch_student(profile_id, expected_auth_user_id=user_id)
        if student is None:
            raise RuntimeError("Created profile could not be loaded")
        session.clear()
        needs_confirmation = getattr(auth_result, "session", None) is None
        if not needs_confirmation:
            session.permanent = True
            session["student_id"] = student["id"]
            session["auth_user_id"] = user_id
        return jsonify({"student": student, "confirmation_required": needs_confirmation}), 201
    except Exception as exc:
        try:
            if profile_id is not None:
                supabase.table("students").delete().eq("id", profile_id).execute()
            if user_id is not None:
                supabase.auth.admin.delete_user(user_id)
        except Exception:
            pass
        message = str(exc).lower()
        if any(text in message for text in ("already registered", "already exists", "user already", "duplicate key")):
            return error("An account with this email already exists.", 409)
        app.logger.exception("Supabase registration failed")
        return error("Unable to create your account. Please check your details and try again.", 400)


@app.route("/api/students", methods=["POST"])
def create_student():
    if session_student() is None:
        return error("Sign in to continue.", 401)
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return error("Send a JSON object with profile details.")
    payload = profile_payload(data)
    if not payload["name"] or not payload["program"] or not payload["year"]:
        return error("Name, program, and year are required.")
    existing = supabase.table("students").select("id").eq("auth_user_id", session["auth_user_id"]).limit(1).execute().data or []
    if existing:
        return error("A student profile already exists for this account.", 409)
    inserted = supabase.table("students").insert({**payload, "auth_user_id": session["auth_user_id"]}).execute().data or []
    if not inserted:
        return error("Unable to create student profile.", 500)
    sid = inserted[0]["id"]
    replace_courses("completed_courses", sid, data.get("completed_courses", []))
    replace_courses("current_courses", sid, data.get("current_courses", []))
    return jsonify({"student": fetch_student(sid)}), 201


@app.route("/api/students/search")
def search_students():
    if supabase is None:
        return error("Supabase is not configured.", 503)
    course = request.args.get("course", "").strip().upper()
    program = request.args.get("program", "").strip()
    year = request.args.get("year", "").strip()
    skills = request.args.get("skills", "").strip()
    advice_topics = request.args.get("advice_topics", "").strip()
    available = request.args.get("available", "true").strip().lower()
    if not any((course, program, year, skills, advice_topics)):
        return jsonify({"students": []})
    try:
        query = supabase.table("students").select("id,name,program,year,skills,advice_topics,willing_to_advise")
        if available != "false":
            query = query.eq("willing_to_advise", True)
        for column, value in (("program", program), ("year", year), ("skills", skills), ("advice_topics", advice_topics)):
            if value:
                query = query.ilike(column, f"%{value}%")
        if course:
            matches = supabase.table("completed_courses").select("student_id").eq("course_code", course).execute().data or []
            ids = sorted({row["student_id"] for row in matches})
            if not ids:
                return jsonify({"students": []})
            query = query.in_("id", ids)
        rows = query.order("name").execute().data or []
        return jsonify({"students": [{**row, "willing_to_advise": bool(row.get("willing_to_advise", False))} for row in rows]})
    except Exception:
        app.logger.exception("Student search failed")
        return error("Unable to search students right now.", 500)


@app.route("/api/students/<int:student_id>")
def student_profile(student_id):
    try:
        student = fetch_student(student_id)
    except Exception:
        app.logger.exception("Profile lookup failed")
        return error("Unable to load this profile right now.", 500)
    if student is None:
        return error("Student not found.", 404)
    return jsonify({"student": student})


@app.route("/api/students/<int:student_id>", methods=["PUT"])
def update_student(student_id):
    if session.get("student_id") is None or not session.get("auth_user_id"):
        return error("Sign in to edit your profile.", 401)
    if session["student_id"] != student_id:
        return error("You can only edit your own profile.", 403)
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return error("Send a JSON object with your profile details.")
    payload = profile_payload(data)
    if not payload["name"] or not payload["program"] or not payload["year"]:
        return error("Name, program, and year are required.")
    if len(payload["name"]) > 100 or len(payload["program"]) > 100 or len(payload["year"]) > 50 or len(payload["bio"]) > 2000 or len(payload["interests"]) > 500:
        return error("One or more profile fields are too long.")
    try:
        rows = supabase.table("students").select("id").eq("id", student_id).eq("auth_user_id", session["auth_user_id"]).limit(1).execute().data or []
        if not rows:
            session.clear()
            return error("Student not found.", 404)
        supabase.table("students").update(payload).eq("id", student_id).eq("auth_user_id", session["auth_user_id"]).execute()
        replace_courses("completed_courses", student_id, data.get("completed_courses", []))
        replace_courses("current_courses", student_id, data.get("current_courses", []))
        return jsonify({"student": fetch_student(student_id, expected_auth_user_id=session["auth_user_id"])})
    except Exception:
        app.logger.exception("Profile update failed")
        return error("Unable to update your profile right now.", 500)


@app.route("/api/students/<int:student_id>/messages", methods=["POST"])
def send_message(student_id):
    return jsonify({"error": "Direct messages have moved to accepted-request conversations. Open Requests to chat."}), 410


if __name__ == "__main__":
    app.run(debug=os.getenv("FLASK_DEBUG", "false").lower() == "true", port=5000)
