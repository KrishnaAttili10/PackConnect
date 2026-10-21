"""Advice requests, participant-only chat, and notifications backed by Supabase."""
from datetime import datetime, timezone
from functools import wraps
from flask import Blueprint, jsonify, request, session


def create_messaging_blueprint(supabase):
    api = Blueprint("messaging", __name__)

    def unavailable():
        return jsonify({"error": "Supabase is not configured."}), 503

    def get_student(student_id):
        if supabase is None:
            return None
        rows = supabase.table("students").select("id,name,auth_user_id,willing_to_advise").eq("id", student_id).limit(1).execute().data or []
        return rows[0] if rows else None

    def authenticated(function):
        @wraps(function)
        def wrapped(*args, **kwargs):
            if supabase is None:
                return unavailable()
            student_id, auth_user_id = session.get("student_id"), session.get("auth_user_id")
            if student_id is None or not auth_user_id:
                return jsonify({"error": "Sign in to continue."}), 401
            rows = supabase.table("students").select("id").eq("id", student_id).eq("auth_user_id", auth_user_id).limit(1).execute().data or []
            if not rows:
                session.clear()
                return jsonify({"error": "Sign in to continue."}), 401
            return function(*args, **kwargs)
        return wrapped

    def get_request(request_id, participant_only=True):
        rows = supabase.table("advice_requests").select("*").eq("id", request_id).limit(1).execute().data or []
        if not rows:
            return None
        record = rows[0]
        if participant_only and session.get("student_id") not in (record["sender_id"], record["recipient_id"]):
            return None
        people = supabase.table("students").select("id,name").in_("id", [record["sender_id"], record["recipient_id"]]).execute().data or []
        names = {person["id"]: person["name"] for person in people}
        record["sender_name"] = names.get(record["sender_id"], "A student")
        record["recipient_name"] = names.get(record["recipient_id"], "A student")
        return record

    def hydrate_requests(rows):
        if not rows:
            return []
        ids = sorted({r["sender_id"] for r in rows} | {r["recipient_id"] for r in rows})
        people = supabase.table("students").select("id,name").in_("id", ids).execute().data or []
        names = {p["id"]: p["name"] for p in people}
        for row in rows:
            row["sender_name"] = names.get(row["sender_id"], "A student")
            row["recipient_name"] = names.get(row["recipient_id"], "A student")
        return rows

    def add_notification(user_id, actor_id, request_id, kind, event_key):
        supabase.table("notifications").insert({
            "user_id": user_id, "actor_id": actor_id, "request_id": request_id,
            "kind": kind, "event_key": event_key,
        }).execute()

    @api.route("/api/requests", methods=["GET"])
    @authenticated
    def list_requests():
        sid = session["student_id"]
        sent = supabase.table("advice_requests").select("*").eq("sender_id", sid).execute().data or []
        received = supabase.table("advice_requests").select("*").eq("recipient_id", sid).execute().data or []
        unique = {row["id"]: row for row in sent + received}
        rows = sorted(unique.values(), key=lambda r: r["id"], reverse=True)
        return jsonify({"requests": hydrate_requests(rows)})

    @api.route("/api/requests", methods=["POST"])
    @authenticated
    def create_request():
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            return jsonify({"error": "Send a JSON object with request details."}), 400
        recipient_id = data.get("recipient_id")
        if type(recipient_id) is not int or recipient_id < 1:
            return jsonify({"error": "Choose a valid recipient."}), 400
        sender_id = session["student_id"]
        if recipient_id == sender_id:
            return jsonify({"error": "You cannot request advice from yourself."}), 400
        fields = {}
        for field, limit in (("course_code", 30), ("advice_topic", 80), ("message", 1000)):
            value = data.get(field)
            if not isinstance(value, str) or not value.strip() or len(value.strip()) > limit:
                return jsonify({"error": f"{field.replace('_', ' ').capitalize()} must contain 1–{limit} characters."}), 400
            fields[field] = value.strip()
        fields["course_code"] = fields["course_code"].upper()
        recipient = get_student(recipient_id)
        if recipient is None:
            return jsonify({"error": "Student not found."}), 404
        if not recipient.get("auth_user_id") or not recipient.get("willing_to_advise"):
            return jsonify({"error": "This student cannot receive advice requests right now."}), 400
        try:
            inserted = supabase.table("advice_requests").insert({"sender_id": sender_id, "recipient_id": recipient_id, **fields}).execute().data or []
            if not inserted:
                return jsonify({"error": "Unable to create advice request."}), 500
            rid = inserted[0]["id"]
            add_notification(recipient_id, sender_id, rid, "request_received", f"request:{rid}")
            return jsonify({"request": get_request(rid)}), 201
        except Exception as exc:
            message = str(exc).lower()
            if any(text in message for text in ("active_advice_pair", "duplicate key", "unique constraint")):
                return jsonify({"error": "You already have a pending request or accepted connection with this student. Open Requests to continue."}), 409
            return jsonify({"error": "Unable to create advice request right now."}), 500

    @api.route("/api/requests/<int:request_id>", methods=["PATCH"])
    @authenticated
    def respond(request_id):
        data = request.get_json(silent=True)
        if not isinstance(data, dict) or data.get("status") not in ("accepted", "declined"):
            return jsonify({"error": "Choose accepted or declined."}), 400
        record = get_request(request_id)
        if record is None:
            return jsonify({"error": "Request not found."}), 404
        if record["recipient_id"] != session["student_id"]:
            return jsonify({"error": "Only the recipient can respond."}), 403
        target = data["status"]
        if record["status"] == target:
            return jsonify({"request": record})
        if record["status"] != "pending":
            return jsonify({"error": "This request has already been handled."}), 409
        changed = supabase.table("advice_requests").update({"status": target}).eq("id", request_id).eq("status", "pending").execute().data or []
        result = get_request(request_id)
        if result is None:
            return jsonify({"error": "Request not found."}), 404
        if result["status"] != target:
            return jsonify({"error": "This request has already been handled."}), 409
        if changed:
            add_notification(record["sender_id"], session["student_id"], request_id, target, f"decision:{request_id}")
        return jsonify({"request": result})

    @api.route("/api/requests/<int:request_id>/messages", methods=["GET", "POST"])
    @authenticated
    def conversation(request_id):
        record = get_request(request_id)
        if record is None:
            return jsonify({"error": "Conversation not found."}), 404
        if record["status"] != "accepted":
            return jsonify({"error": "Chat unlocks when the request is accepted."}), 403
        if request.method == "POST":
            data = request.get_json(silent=True)
            body = data.get("body") if isinstance(data, dict) else None
            if not isinstance(body, str) or not body.strip() or len(body.strip()) > 2000:
                return jsonify({"error": "Messages must contain 1–2000 characters."}), 400
            inserted = supabase.table("chat_messages").insert({"request_id": request_id, "sender_id": session["student_id"], "body": body.strip()}).execute().data or []
            if not inserted:
                return jsonify({"error": "Unable to send message."}), 500
            message = inserted[0]
            peer_id = record["recipient_id"] if record["sender_id"] == session["student_id"] else record["sender_id"]
            add_notification(peer_id, session["student_id"], request_id, "message", f"message:{message['id']}")
            return jsonify({"message": message}), 201
        cursor = request.args.get("after_id", "0")
        if not cursor.isascii() or not cursor.isdigit() or len(cursor) > 18:
            return jsonify({"error": "Invalid message cursor."}), 400
        rows = supabase.table("chat_messages").select("*").eq("request_id", request_id).gt("id", int(cursor)).order("id").limit(101).execute().data or []
        return jsonify({"request": record, "messages": rows[:100], "has_more": len(rows) > 100})

    @api.route("/api/notifications", methods=["GET"])
    @authenticated
    def list_notifications():
        uid = session["student_id"]
        rows = supabase.table("notifications").select("id,user_id,actor_id,request_id,kind,read_at,created_at").eq("user_id", uid).order("id", desc=True).limit(50).execute().data or []
        unread = supabase.table("notifications").select("id").eq("user_id", uid).is_("read_at", "null").execute().data or []
        if not rows:
            return jsonify({"notifications": [], "unread_count": len(unread)})
        actor_ids = sorted({r["actor_id"] for r in rows})
        request_ids = sorted({r["request_id"] for r in rows})
        people = supabase.table("students").select("id,name").in_("id", actor_ids).execute().data or []
        requests = supabase.table("advice_requests").select("id,course_code").in_("id", request_ids).execute().data or []
        names = {r["id"]: r["name"] for r in people}
        courses = {r["id"]: r["course_code"] for r in requests}
        result = [{
            "id": row["id"], "request_id": row["request_id"], "kind": row["kind"],
            "read_at": row["read_at"], "created_at": row["created_at"],
            "actor_name": names.get(row["actor_id"], "A student"),
            "course_code": courses.get(row["request_id"]),
        } for row in rows]
        return jsonify({"notifications": result, "unread_count": len(unread)})

    @api.route("/api/notifications/<int:notification_id>/read", methods=["POST"])
    @authenticated
    def read_notification(notification_id):
        uid = session["student_id"]
        rows = supabase.table("notifications").select("id,read_at").eq("id", notification_id).eq("user_id", uid).limit(1).execute().data or []
        if not rows:
            return jsonify({"error": "Notification not found."}), 404
        if rows[0].get("read_at") is None:
            supabase.table("notifications").update({"read_at": datetime.now(timezone.utc).isoformat()}).eq("id", notification_id).eq("user_id", uid).is_("read_at", "null").execute()
        return jsonify({"status": "ok"})

    @api.route("/api/notifications/read", methods=["POST"])
    @authenticated
    def read_all_notifications():
        data = request.get_json(silent=True)
        cutoff = data.get("through_id") if isinstance(data, dict) else None
        if type(cutoff) is not int or not 0 <= cutoff <= 9223372036854775807:
            return jsonify({"error": "Provide a valid notification ID cutoff."}), 400
        supabase.table("notifications").update({"read_at": datetime.now(timezone.utc).isoformat()}).eq("user_id", session["student_id"]).is_("read_at", "null").lte("id", cutoff).execute()
        return jsonify({"status": "ok"})

    return api
