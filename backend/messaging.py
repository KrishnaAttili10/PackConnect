"""Persistent advice requests and participant-only conversations."""

from psycopg.errors import UniqueViolation
from functools import wraps
from contextlib import nullcontext

from flask import Blueprint, g, jsonify, request, session
from identity import registered_student_sql, session_student_id
from availability import advisor_availability
from lifecycle import blocked, expire_requests, lock_students, notify


def initialize_messaging(db):
    db.execute("""
        INSERT INTO notifications (user_id, actor_id, request_id, kind, event_key)
        SELECT recipient_id, sender_id, id, 'request_received', 'request:' || id
        FROM advice_requests WHERE status = 'pending'
        ON CONFLICT (event_key) DO NOTHING
    """)
    db.execute("""
        INSERT INTO notifications (user_id, actor_id, request_id, kind, event_key)
        SELECT sender_id, recipient_id, id, status, 'decision:' || id
        FROM advice_requests WHERE status IN ('accepted', 'declined')
        ON CONFLICT (event_key) DO NOTHING
    """)


def create_messaging_blueprint(get_db):
    api = Blueprint("messaging", __name__)

    def authenticated(function):
        @wraps(function)
        def wrapped(*args, **kwargs):
            with get_db() as db:
                student_id = session_student_id(db, session)
                if student_id is None:
                    return jsonify({"error": "Sign in to continue."}), 401
                g.messaging_db = db
                try:
                    return function(*args, **kwargs)
                finally:
                    g.pop("messaging_db", None)
        return wrapped

    def request_database():
        # Authentication and the route use one connection and transaction.
        return nullcontext(g.messaging_db)

    def get_request(db, request_id, lock=False):
        row = db.execute("""
            SELECT r.*, s.name AS sender_name, t.name AS recipient_name
            FROM advice_requests r
            JOIN students s ON s.id = r.sender_id
            JOIN students t ON t.id = r.recipient_id
            WHERE r.id = %s AND (r.sender_id = %s OR r.recipient_id = %s)
        """ + (" FOR UPDATE OF r" if lock else ""),
                         (request_id, session["student_id"], session["student_id"])).fetchone()
        return dict(row) if row else None

    @api.route("/api/requests", methods=["GET"])
    @authenticated
    def list_requests():
        with request_database() as db:
            expire_requests(db, student_id=session["student_id"])
            rows = db.execute("""
                SELECT r.*, s.name AS sender_name, t.name AS recipient_name
                FROM advice_requests r
                JOIN students s ON s.id = r.sender_id
                JOIN students t ON t.id = r.recipient_id
                WHERE r.sender_id = %s OR r.recipient_id = %s
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
            with request_database() as db:
                lock_students(db, session["student_id"], recipient_id)
                expire_requests(db, recipient_id=recipient_id)
                if blocked(db, session["student_id"], recipient_id):
                    return jsonify(error="Contact is unavailable for this student."), 403
                recipient = db.execute(f"""
                    SELECT s.willing_to_advise, {registered_student_sql()} AS can_receive_requests
                    FROM students s WHERE s.id = %s FOR NO KEY UPDATE OF s
                """, (recipient_id,)).fetchone()
                if recipient is None:
                    return jsonify({"error": "Student not found."}), 404
                if not recipient["willing_to_advise"] or not recipient["can_receive_requests"]:
                    return jsonify({"error": "This student cannot receive advice requests right now."}), 400
                availability = advisor_availability(db, recipient_id)
                if not availability["accepting_requests"]:
                    message = (f"This advisor has paused new requests until {availability['pause_until'].isoformat()} (Eastern time)."
                               if availability["availability_status"] == "paused"
                               else "This advisor is at their open-request limit. Try another advisor or check back later.")
                    return jsonify({"error": message}), 409
                cursor = db.execute("""
                    INSERT INTO advice_requests
                    (sender_id, recipient_id, course_code, advice_topic, message)
                    VALUES (%s, %s, %s, %s, %s) RETURNING id
                """, (session["student_id"], recipient_id, fields["course_code"],
                      fields["advice_topic"], fields["message"]))
                result = get_request(db, cursor.fetchone()["id"])
                db.execute("""
                    INSERT INTO notifications (user_id, actor_id, request_id, kind, event_key)
                    VALUES (%s, %s, %s, 'request_received', %s)
                """, (recipient_id, session["student_id"], result["id"], f"request:{result['id']}"))
        except UniqueViolation:
            return jsonify({"error": "You already have a pending request or accepted connection with this student. Open Requests to continue."}), 409
        return jsonify({"request": result}), 201

    @api.route("/api/requests/<int:request_id>", methods=["PATCH"])
    @authenticated
    def respond(request_id):
        data = request.get_json(silent=True)
        if not isinstance(data, dict) or data.get("status") not in ("accepted", "declined", "completed", "cancelled"):
            return jsonify({"error": "Choose accepted, declined, completed, or cancelled."}), 400
        with request_database() as db:
            record = get_request(db, request_id)
            if record is None:
                return jsonify({"error": "Request not found."}), 404
            lock_students(db, record["sender_id"], record["recipient_id"])
            expire_requests(db, recipient_id=record["recipient_id"])
            record = get_request(db, request_id, lock=True)
            if data["status"] == "cancelled":
                if record["sender_id"] != session["student_id"]:
                    return jsonify(error="Only the sender can cancel a pending request."),403
                if record["status"] not in ("pending", "cancelled"):
                    return jsonify(error="Only pending requests can be cancelled."),409
                if record["status"] == "pending":
                    db.execute("UPDATE advice_requests SET status='cancelled' WHERE id=%s",(request_id,))
                    notify(db,record["recipient_id"],record["sender_id"],request_id,"cancelled",f"cancelled:{request_id}")
                return jsonify(request=get_request(db,request_id))
            if data["status"] == "completed":
                if record["status"] not in ("accepted", "completed"):
                    return jsonify({"error": "Only accepted advice can be completed."}), 409
                db.execute("UPDATE advice_requests SET status = 'completed' WHERE id = %s", (request_id,))
                db.execute("UPDATE advice_meetings SET status='cancelled' WHERE request_id=%s AND status IN ('proposed','accepted') AND ends_at>now()",(request_id,))
                return jsonify({"request": get_request(db, request_id)})
            if record["recipient_id"] != session["student_id"]:
                return jsonify({"error": "Only the recipient can respond."}), 403
            changed = db.execute("UPDATE advice_requests SET status = %s WHERE id = %s AND status = 'pending'",
                                 (data["status"], request_id)).rowcount
            result = get_request(db, request_id)
            if result["status"] != data["status"]:
                return jsonify({"error": "This request has already been handled."}), 409
            if changed:
                db.execute("""
                    INSERT INTO notifications (user_id, actor_id, request_id, kind, event_key)
                    VALUES (%s, %s, %s, %s, %s) ON CONFLICT (event_key) DO NOTHING
                """, (record["sender_id"], session["student_id"], request_id,
                      data["status"], f"decision:{request_id}"))
        return jsonify({"request": result})

    @api.route("/api/requests/<int:request_id>/messages", methods=["GET", "POST"])
    @authenticated
    def conversation(request_id):
        with request_database() as db:
            record = get_request(db, request_id)
            if record is None:
                return jsonify({"error": "Conversation not found."}), 404
            lock_students(db,record["sender_id"],record["recipient_id"])
            record = get_request(db, request_id, lock=True)
            contact_allowed = not blocked(db,record["sender_id"],record["recipient_id"])
            if record["status"] not in ("accepted", "completed", "closed"):
                return jsonify({"error": "Chat unlocks when the request is accepted."}), 403
            if request.method == "POST":
                if not contact_allowed:
                    return jsonify(error="Contact is unavailable for this student."),403
                if record["status"] in ("completed", "closed"):
                    return jsonify({"error": "This advice is complete. Message history is read-only."}), 409
                data = request.get_json(silent=True)
                body = data.get("body") if isinstance(data, dict) else None
                if not isinstance(body, str) or not body.strip() or len(body.strip()) > 2000:
                    return jsonify({"error": "Messages must contain 1–2000 characters."}), 400
                cursor = db.execute("INSERT INTO chat_messages (request_id, sender_id, body) VALUES (%s, %s, %s) RETURNING id",
                                    (request_id, session["student_id"], body.strip()))
                row = db.execute("SELECT * FROM chat_messages WHERE id = %s", (cursor.fetchone()["id"],)).fetchone()
                peer_id = record["recipient_id"] if record["sender_id"] == session["student_id"] else record["sender_id"]
                db.execute("""
                    INSERT INTO notifications (user_id, actor_id, request_id, kind, event_key)
                    VALUES (%s, %s, %s, 'message', %s)
                """, (peer_id, session["student_id"], request_id, f"message:{row['id']}"))
                return jsonify({"message": dict(row)}), 201
            after_id = request.args.get("after_id", "0")
            if not after_id.isascii() or not after_id.isdigit() or len(after_id) > 18:
                return jsonify({"error": "Invalid message cursor."}), 400
            rows = db.execute("""
                SELECT * FROM chat_messages WHERE request_id = %s AND id > %s
                ORDER BY id LIMIT 101
            """, (request_id, int(after_id))).fetchall()
            visible = rows[:100]
            if visible:
                db.execute("""INSERT INTO conversation_reads(user_id,request_id,last_read_id) VALUES(%s,%s,%s)
                    ON CONFLICT(user_id,request_id) DO UPDATE SET last_read_id=GREATEST(conversation_reads.last_read_id,EXCLUDED.last_read_id)""",
                    (session["student_id"],request_id,visible[-1]["id"]))
            record["contact_allowed"] = contact_allowed
        return jsonify({"request": record, "messages": [dict(row) for row in visible], "has_more": len(rows) > 100})

    @api.route("/api/notifications", methods=["GET"])
    @authenticated
    def list_notifications():
        with request_database() as db:
            rows = db.execute("""
                SELECT n.id, n.request_id, n.kind, n.read_at, n.created_at,
                       COALESCE(s.name, 'A student') AS actor_name, r.course_code
                FROM notifications n
                LEFT JOIN students s ON s.id = n.actor_id
                JOIN advice_requests r ON r.id = n.request_id
                WHERE n.user_id = %s ORDER BY n.id DESC LIMIT 50
            """, (session["student_id"],)).fetchall()
            unread = db.execute("SELECT COUNT(*) FROM notifications WHERE user_id = %s AND read_at IS NULL",
                                (session["student_id"],)).fetchone()["count"]
        return jsonify({"notifications": [dict(row) for row in rows], "unread_count": unread})

    @api.route("/api/notifications/<int:notification_id>/read", methods=["POST"])
    @authenticated
    def read_notification(notification_id):
        with request_database() as db:
            result = db.execute("""
                WITH marked AS (
                    UPDATE notifications SET read_at = COALESCE(read_at, CURRENT_TIMESTAMP)
                    WHERE id = %s AND user_id = %s RETURNING id
                )
                SELECT (SELECT count(*) FROM marked) AS changed,
                       count(*) AS unread_count FROM notifications
                WHERE user_id = %s AND read_at IS NULL AND id <> %s
            """, (notification_id, session["student_id"], session["student_id"], notification_id)).fetchone()
            if not result["changed"]:
                return jsonify({"error": "Notification not found."}), 404
        return jsonify({"status": "ok", "unread_count": result["unread_count"]})

    @api.route("/api/notifications/read", methods=["POST"])
    @authenticated
    def read_all_notifications():
        data = request.get_json(silent=True)
        through_id = data.get("through_id") if isinstance(data, dict) else None
        if type(through_id) is not int or not 0 <= through_id <= 9223372036854775807:
            return jsonify({"error": "Provide a valid notification ID cutoff."}), 400
        with request_database() as db:
            result = db.execute("""
                WITH marked AS (
                    UPDATE notifications SET read_at = CURRENT_TIMESTAMP
                    WHERE user_id = %s AND read_at IS NULL AND id <= %s RETURNING id
                )
                SELECT count(*) AS unread_count FROM notifications
                WHERE user_id = %s AND read_at IS NULL AND id > %s
            """, (session["student_id"], through_id, session["student_id"], through_id)).fetchone()
        return jsonify({"status": "ok", "unread_count": result["unread_count"]})

    return api
