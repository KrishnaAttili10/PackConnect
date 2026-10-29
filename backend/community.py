"""Participant inbox, contact controls, reports, and moderator review."""

from functools import wraps

from flask import Blueprint, jsonify, request, session
from identity import session_student_id
from lifecycle import blocked, expire_requests, lock_students


def create_community_blueprint(get_db):
    api = Blueprint("community", __name__)

    def authenticated(function):
        @wraps(function)
        def wrapped(*args, **kwargs):
            with get_db() as db:
                user = session_student_id(db, session)
                if user is None:
                    return jsonify(error="Sign in to continue."), 401
                return function(db, user, *args, **kwargs)

        return wrapped

    @api.get("/api/conversations")
    @authenticated
    def inbox(db, user):
        expire_requests(db, student_id=user)
        rows = db.execute(
            """SELECT r.id, r.status, r.course_code, r.advice_topic,
            CASE WHEN r.sender_id = %s THEN t.id ELSE s.id END AS peer_id,
            CASE WHEN r.sender_id = %s THEN t.name ELSE s.name END AS peer_name,
            last.body AS latest_message, COALESCE(last.created_at,r.created_at) AS updated_at,
            (SELECT count(*) FROM chat_messages m WHERE m.request_id=r.id AND m.sender_id<>%s
             AND m.id>COALESCE(seen.last_read_id,0)) AS unread_count
            FROM advice_requests r JOIN students s ON s.id=r.sender_id JOIN students t ON t.id=r.recipient_id
            LEFT JOIN conversation_reads seen ON seen.request_id=r.id AND seen.user_id=%s
            LEFT JOIN LATERAL (SELECT body,created_at FROM chat_messages WHERE request_id=r.id ORDER BY id DESC LIMIT 1) last ON true
            WHERE (r.sender_id=%s OR r.recipient_id=%s) AND r.status IN ('accepted','completed','closed')
            ORDER BY updated_at DESC,r.id DESC""",
            (user, user, user, user, user, user),
        ).fetchall()
        return jsonify(conversations=[dict(row) for row in rows])

    @api.get("/api/blocks")
    @authenticated
    def blocks(db, user):
        rows = db.execute(
            """SELECT s.id,s.name FROM student_blocks b JOIN students s ON s.id=b.blocked_id
            WHERE b.blocker_id=%s ORDER BY s.name""",
            (user,),
        ).fetchall()
        return jsonify(blocks=[dict(row) for row in rows])

    @api.route("/api/students/<int:student_id>/block", methods=["POST", "DELETE"])
    @authenticated
    def block_student(db, user, student_id):
        if student_id == user:
            return jsonify(error="You cannot block yourself."), 400
        lock_students(db, user, student_id)
        if not db.execute(
            "SELECT id FROM students WHERE id=%s", (student_id,)
        ).fetchone():
            return jsonify(error="Student not found."), 404
        if request.method == "DELETE":
            db.execute(
                "DELETE FROM student_blocks WHERE blocker_id=%s AND blocked_id=%s",
                (user, student_id),
            )
        else:
            db.execute(
                "INSERT INTO student_blocks(blocker_id,blocked_id) VALUES(%s,%s) ON CONFLICT DO NOTHING",
                (user, student_id),
            )
            db.execute(
                """UPDATE advice_requests SET status='closed' WHERE status IN ('pending','accepted')
                AND ((sender_id=%s AND recipient_id=%s) OR (sender_id=%s AND recipient_id=%s))""",
                (user, student_id, student_id, user),
            )
            db.execute(
                """UPDATE advice_meetings m SET status='cancelled' FROM advice_requests r
                WHERE m.request_id=r.id AND m.status IN ('proposed','accepted') AND m.ends_at>now()
                AND ((r.sender_id=%s AND r.recipient_id=%s) OR (r.sender_id=%s AND r.recipient_id=%s))""",
                (user, student_id, student_id, user),
            )
        return jsonify(status="ok", blocked=request.method == "POST")

    @api.post("/api/students/<int:student_id>/reports")
    @authenticated
    def report(db, user, student_id):
        data = request.get_json(silent=True)
        if (
            not isinstance(data, dict)
            or not isinstance(data.get("reason"), str)
            or not 1 <= len(data["reason"].strip()) <= 2000
        ):
            return jsonify(error="Describe the concern in 1–2000 characters."), 400
        if (
            student_id == user
            or not db.execute(
                "SELECT id FROM students WHERE id=%s", (student_id,)
            ).fetchone()
        ):
            return jsonify(error="Choose another student to report."), 400
        message_id = data.get("message_id")
        if message_id is not None:
            if (
                type(message_id) is not int
                or not db.execute(
                    """SELECT m.id FROM chat_messages m JOIN advice_requests r ON r.id=m.request_id
                WHERE m.id=%s AND m.sender_id=%s AND (r.sender_id=%s OR r.recipient_id=%s)""",
                    (message_id, student_id, user, user),
                ).fetchone()
            ):
                return (
                    jsonify(
                        error="You can only report messages shared with you by this student."
                    ),
                    400,
                )
        count = db.execute(
            "SELECT count(*) AS n FROM student_reports WHERE reporter_id=%s AND created_at>now()-interval '1 day'",
            (user,),
        ).fetchone()["n"]
        if count >= 10:
            return (
                jsonify(error="Daily report limit reached. Please try again later."),
                429,
            )
        row = db.execute(
            "INSERT INTO student_reports(reporter_id,reported_id,message_id,reason) VALUES(%s,%s,%s,%s) RETURNING id",
            (user, student_id, message_id, data["reason"].strip()),
        ).fetchone()
        return jsonify(report_id=row["id"], status="open"), 201

    @api.route("/api/moderation/reports", methods=["GET"])
    @api.route("/api/moderation/reports/<int:report_id>", methods=["PATCH"])
    @authenticated
    def moderation(db, user, report_id=None):
        if not db.execute(
            "SELECT 1 FROM staff_members WHERE student_id=%s", (user,)
        ).fetchone():
            return jsonify(error="Moderator access required."), 403
        if request.method == "PATCH":
            data = request.get_json(silent=True)
            if (
                not isinstance(data, dict)
                or data.get("status") not in ("resolved", "dismissed")
                or not isinstance(data.get("resolution"), str)
                or not 1 <= len(data["resolution"].strip()) <= 2000
            ):
                return (
                    jsonify(
                        error="Choose resolved or dismissed and provide a resolution of 1–2000 characters."
                    ),
                    400,
                )
            changed = db.execute(
                "UPDATE student_reports SET status=%s,resolution=%s,reviewed_by=%s WHERE id=%s AND status='open'",
                (data["status"], data["resolution"].strip(), user, report_id),
            ).rowcount
            if not changed:
                return jsonify(error="Open report not found."), 404
            return jsonify(status="ok")
        rows = db.execute(
            """SELECT r.*,s.name AS reporter_name,t.name AS reported_name,m.body AS message_body
            FROM student_reports r JOIN students s ON s.id=r.reporter_id JOIN students t ON t.id=r.reported_id
            LEFT JOIN chat_messages m ON m.id=r.message_id ORDER BY (r.status='open') DESC,r.id DESC LIMIT 100"""
        ).fetchall()
        return jsonify(reports=[dict(row) for row in rows])

    return api
