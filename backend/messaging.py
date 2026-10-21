"""Persistent advice requests and participant-only conversations."""

import sqlite3
from functools import wraps

from flask import Blueprint, jsonify, request, session


def initialize_messaging(db):
    db.executescript("""
        CREATE TABLE IF NOT EXISTS advice_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sender_id INTEGER NOT NULL REFERENCES students(id),
            recipient_id INTEGER NOT NULL REFERENCES students(id),
            course_code TEXT NOT NULL,
            advice_topic TEXT NOT NULL,
            message TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending'
                CHECK(status IN ('pending', 'accepted', 'declined')),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CHECK(sender_id != recipient_id)
        );
        CREATE UNIQUE INDEX IF NOT EXISTS active_advice_pair
        ON advice_requests(min(sender_id, recipient_id), max(sender_id, recipient_id))
        WHERE status IN ('pending', 'accepted');
        CREATE TABLE IF NOT EXISTS chat_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            request_id INTEGER NOT NULL REFERENCES advice_requests(id),
            sender_id INTEGER NOT NULL REFERENCES students(id),
            body TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS chat_request_cursor
        ON chat_messages(request_id, id);
    """)


def create_messaging_blueprint(get_db):
    api = Blueprint("messaging", __name__)

    def authenticated(function):
        @wraps(function)
        def wrapped(*args, **kwargs):
            with get_db() as db:
                account = db.execute(
                    "SELECT student_id FROM accounts WHERE student_id = ?",
                    (session.get("student_id"),),
                ).fetchone()
            if account is None:
                return jsonify({"error": "Sign in to continue."}), 401
            return function(*args, **kwargs)
        return wrapped

    def get_request(db, request_id):
        row = db.execute("""
            SELECT r.*, s.name AS sender_name, t.name AS recipient_name
            FROM advice_requests r
            JOIN students s ON s.id = r.sender_id
            JOIN students t ON t.id = r.recipient_id
            WHERE r.id = ? AND (r.sender_id = ? OR r.recipient_id = ?)
        """, (request_id, session["student_id"], session["student_id"])).fetchone()
        return dict(row) if row else None

    @api.route("/api/requests", methods=["GET"])
    @authenticated
    def list_requests():
        with get_db() as db:
            rows = db.execute("""
                SELECT r.*, s.name AS sender_name, t.name AS recipient_name
                FROM advice_requests r
                JOIN students s ON s.id = r.sender_id
                JOIN students t ON t.id = r.recipient_id
                WHERE r.sender_id = ? OR r.recipient_id = ?
                ORDER BY r.id DESC
            """, (session["student_id"], session["student_id"])).fetchall()
        return jsonify({"requests": [dict(row) for row in rows]})

    @api.route("/api/requests", methods=["POST"])
    @authenticated
    def create_request():
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            return jsonify({"error": "Send a JSON object with request details."}), 400
        recipient_id = data.get("recipient_id")
        if type(recipient_id) is not int or recipient_id < 1:
            return jsonify({"error": "Choose a valid recipient."}), 400
        if recipient_id == session["student_id"]:
            return jsonify({"error": "You cannot request advice from yourself."}), 400
        fields = {}
        for field, limit in [("course_code", 30), ("advice_topic", 80), ("message", 1000)]:
            value = data.get(field)
            if not isinstance(value, str) or not value.strip() or len(value.strip()) > limit:
                return jsonify({"error": f"{field.replace('_', ' ').capitalize()} must contain 1–{limit} characters."}), 400
            fields[field] = value.strip()
        fields["course_code"] = fields["course_code"].upper()
        try:
            with get_db() as db:
                recipient = db.execute("""
                    SELECT s.willing_to_advise, a.id AS account_id FROM students s
                    LEFT JOIN accounts a ON a.student_id = s.id WHERE s.id = ?
                """, (recipient_id,)).fetchone()
                if recipient is None:
                    return jsonify({"error": "Student not found."}), 404
                if not recipient["willing_to_advise"] or recipient["account_id"] is None:
                    return jsonify({"error": "This student cannot receive advice requests right now."}), 400
                cursor = db.execute("""
                    INSERT INTO advice_requests
                    (sender_id, recipient_id, course_code, advice_topic, message)
                    VALUES (?, ?, ?, ?, ?)
                """, (session["student_id"], recipient_id, fields["course_code"],
                      fields["advice_topic"], fields["message"]))
                result = get_request(db, cursor.lastrowid)
        except sqlite3.IntegrityError:
            return jsonify({"error": "You already have a pending request or accepted connection with this student. Open Requests to continue."}), 409
        return jsonify({"request": result}), 201

    @api.route("/api/requests/<int:request_id>", methods=["PATCH"])
    @authenticated
    def respond(request_id):
        data = request.get_json(silent=True)
        if not isinstance(data, dict) or data.get("status") not in ("accepted", "declined"):
            return jsonify({"error": "Choose accepted or declined."}), 400
        with get_db() as db:
            record = get_request(db, request_id)
            if record is None:
                return jsonify({"error": "Request not found."}), 404
            if record["recipient_id"] != session["student_id"]:
                return jsonify({"error": "Only the recipient can respond."}), 403
            db.execute("UPDATE advice_requests SET status = ? WHERE id = ? AND status = 'pending'",
                       (data["status"], request_id))
            result = get_request(db, request_id)
            if result["status"] != data["status"]:
                return jsonify({"error": "This request has already been handled."}), 409
        return jsonify({"request": result})

    @api.route("/api/requests/<int:request_id>/messages", methods=["GET", "POST"])
    @authenticated
    def conversation(request_id):
        with get_db() as db:
            record = get_request(db, request_id)
            if record is None:
                return jsonify({"error": "Conversation not found."}), 404
            if record["status"] != "accepted":
                return jsonify({"error": "Chat unlocks when the request is accepted."}), 403
            if request.method == "POST":
                data = request.get_json(silent=True)
                body = data.get("body") if isinstance(data, dict) else None
                if not isinstance(body, str) or not body.strip() or len(body.strip()) > 2000:
                    return jsonify({"error": "Messages must contain 1–2000 characters."}), 400
                cursor = db.execute("INSERT INTO chat_messages (request_id, sender_id, body) VALUES (?, ?, ?)",
                                    (request_id, session["student_id"], body.strip()))
                row = db.execute("SELECT * FROM chat_messages WHERE id = ?", (cursor.lastrowid,)).fetchone()
                return jsonify({"message": dict(row)}), 201
            after_id = request.args.get("after_id", "0")
            if not after_id.isascii() or not after_id.isdigit() or len(after_id) > 18:
                return jsonify({"error": "Invalid message cursor."}), 400
            rows = db.execute("""
                SELECT * FROM chat_messages WHERE request_id = ? AND id > ?
                ORDER BY id LIMIT 101
            """, (request_id, int(after_id))).fetchall()
        return jsonify({"request": record, "messages": [dict(row) for row in rows[:100]], "has_more": len(rows) > 100})

    return api
