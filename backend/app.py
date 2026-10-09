
from flask import Flask, jsonify, request
from flask_cors import CORS
import sqlite3
from pathlib import Path
from contextlib import contextmanager

app = Flask(__name__)
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

        db.execute("""
            CREATE TABLE IF NOT EXISTS completed_courses (
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
                    (name, program, year, bio, interests, willing_to_advise)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (name, program, year, bio, interests, willing))

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


@app.route("/api/students/search")
def search_students():
    course = request.args.get("course", "").strip().upper()

    if not course:
        return jsonify({"students": []})

    with get_db() as db:
        rows = db.execute("""
            SELECT DISTINCT
                s.id,
                s.name,
                s.program,
                s.year
            FROM students s
            JOIN completed_courses c ON s.id = c.student_id
            WHERE UPPER(c.course_code) = ?
              AND s.willing_to_advise = 1
            ORDER BY s.name
        """, (course,)).fetchall()

    return jsonify({
        "students": [dict(row) for row in rows]
    })


@app.route("/api/students/<int:student_id>")
def student_profile(student_id):
    with get_db() as db:
        student = db.execute("""
            SELECT *
            FROM students
            WHERE id = ?
        """, (student_id,)).fetchone()

        if student is None:
            return jsonify({"error": "Student not found"}), 404

        courses = db.execute("""
            SELECT course_code
            FROM completed_courses
            WHERE student_id = ?
            ORDER BY course_code
        """, (student_id,)).fetchall()

    profile = dict(student)
    profile["completed_courses"] = [
        row["course_code"] for row in courses
    ]

    return jsonify({"student": profile})


@app.route("/api/students/<int:student_id>/messages", methods=["POST"])
def send_message(student_id):
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "Send a JSON object with sender_name and body."}), 400

    sender_name = data.get("sender_name")
    body = data.get("body")
    if not isinstance(sender_name, str) or not sender_name.strip():
        return jsonify({"error": "Please enter your name."}), 400
    if not isinstance(body, str) or not body.strip():
        return jsonify({"error": "Please enter a message."}), 400
    sender_name, body = sender_name.strip(), body.strip()
    if len(sender_name) > 100 or len(body) > 2000:
        return jsonify({"error": "Name must be at most 100 characters and message at most 2000 characters."}), 400

    with get_db() as db:
        student = db.execute(
            "SELECT willing_to_advise FROM students WHERE id = ?", (student_id,)
        ).fetchone()
        if student is None:
            return jsonify({"error": "Student not found"}), 404
        if not student["willing_to_advise"]:
            return jsonify({"error": "This student is not currently accepting advice messages."}), 403
        cursor = db.execute("""
            INSERT INTO messages (recipient_id, sender_name, body)
            VALUES (?, ?, ?)
        """, (student_id, sender_name, body))
        message = db.execute(
            "SELECT * FROM messages WHERE id = ?", (cursor.lastrowid,)
        ).fetchone()

    return jsonify({"message": dict(message)}), 201


if __name__ == "__main__":
    initialize_database()
    app.run(debug=True, port=5000)
