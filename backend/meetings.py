"""Meeting proposals with participant approval, conflict checks, and calendar export."""

from datetime import datetime, timedelta, timezone
from functools import wraps

from flask import Blueprint, Response, jsonify, request, session
from psycopg.errors import UniqueViolation
from identity import session_student_id
from lifecycle import blocked, lock_students, notify


def calendar_escape(value):
    return (
        value.replace("\\", "\\\\")
        .replace("\r", "")
        .replace("\n", "\\n")
        .replace(";", "\\;")
        .replace(",", "\\,")
    )


def create_meetings_blueprint(get_db):
    api = Blueprint("meetings", __name__)

    def participant(function):
        @wraps(function)
        def wrapped(request_id, *args, **kwargs):
            with get_db() as db:
                user = session_student_id(db, session)
                if user is None:
                    return jsonify(error="Sign in to continue."), 401
                record = db.execute(
                    "SELECT * FROM advice_requests WHERE id=%s AND (sender_id=%s OR recipient_id=%s)",
                    (request_id, user, user),
                ).fetchone()
                if not record:
                    return jsonify(error="Conversation not found."), 404
                lock_students(db, record["sender_id"], record["recipient_id"])
                record = db.execute(
                    "SELECT * FROM advice_requests WHERE id=%s FOR UPDATE",
                    (request_id,),
                ).fetchone()
                return function(db, user, record, *args, **kwargs)

        return wrapped

    @api.route("/api/requests/<int:request_id>/meetings", methods=["GET", "POST"])
    @participant
    def meetings(db, user, record):
        if request.method == "GET":
            rows = db.execute(
                "SELECT * FROM advice_meetings WHERE request_id=%s ORDER BY starts_at DESC,id DESC",
                (record["id"],),
            ).fetchall()
            return jsonify(meetings=[dict(row) for row in rows])
        if record["status"] != "accepted" or blocked(
            db, record["sender_id"], record["recipient_id"]
        ):
            return (
                jsonify(
                    error="Schedule meetings only in an active, unblocked conversation."
                ),
                409,
            )
        data = request.get_json(silent=True)
        try:
            if not isinstance(data, dict):
                raise ValueError()
            start = datetime.fromisoformat(data["starts_at"].replace("Z", "+00:00"))
            end = datetime.fromisoformat(data["ends_at"].replace("Z", "+00:00"))
            if start.utcoffset() is None or end.utcoffset() is None:
                raise ValueError()
            now = datetime.now(timezone.utc)
            if not now < start <= now + timedelta(days=180) or not timedelta(
                minutes=15
            ) <= end - start <= timedelta(hours=2):
                raise ValueError()
            location = data["location"].strip()
            if not 1 <= len(location) <= 300:
                raise ValueError()
        except (KeyError, ValueError, TypeError, AttributeError, OverflowError):
            return (
                jsonify(
                    error="Choose a future time within 180 days, a duration of 15–120 minutes, and a meeting location or link (1–300 characters)."
                ),
                400,
            )
        db.execute(
            "UPDATE advice_meetings SET status='declined' WHERE request_id=%s AND status='proposed' AND starts_at<=now()",
            (record["id"],),
        )
        if db.execute(
            "SELECT 1 FROM advice_meetings WHERE request_id=%s AND (status='proposed' OR (status='accepted' AND ends_at>now()))",
            (record["id"],),
        ).fetchone():
            return (
                jsonify(error="Respond to or cancel the existing meeting first."),
                409,
            )
        row = db.execute(
            "INSERT INTO advice_meetings(request_id,proposer_id,starts_at,ends_at,location) VALUES(%s,%s,%s,%s,%s) RETURNING *",
            (record["id"], user, start, end, location),
        ).fetchone()
        peer = (
            record["recipient_id"]
            if user == record["sender_id"]
            else record["sender_id"]
        )
        notify(db, peer, user, record["id"], "meeting", f"meeting:{row['id']}:proposed")
        return jsonify(meeting=dict(row)), 201

    @api.patch("/api/requests/<int:request_id>/meetings/<int:meeting_id>")
    @participant
    def decide(db, user, record, meeting_id):
        row = db.execute(
            "SELECT * FROM advice_meetings WHERE id=%s AND request_id=%s FOR UPDATE",
            (meeting_id, record["id"]),
        ).fetchone()
        if not row:
            return jsonify(error="Meeting not found."), 404
        data = request.get_json(silent=True)
        status = data.get("status") if isinstance(data, dict) else None
        if status not in ("accepted", "declined", "cancelled"):
            return jsonify(error="Choose accepted, declined, or cancelled."), 400
        if status == "cancelled":
            if row["status"] not in ("proposed", "accepted", "cancelled"):
                return jsonify(error="This meeting has already been handled."), 409
        else:
            if row["proposer_id"] == user:
                return (
                    jsonify(error="The other student must respond to the proposal."),
                    403,
                )
            if record["status"] != "accepted" or blocked(
                db, record["sender_id"], record["recipient_id"]
            ):
                return (
                    jsonify(error="This conversation is not available for scheduling."),
                    409,
                )
            if row["status"] != "proposed" or row["starts_at"] <= datetime.now(
                timezone.utc
            ):
                return jsonify(error="This proposal is no longer available."), 409
        if status == "accepted":
            conflict = db.execute(
                """SELECT 1 FROM advice_meetings m JOIN advice_requests r ON r.id=m.request_id
                WHERE m.status='accepted' AND m.id<>%s AND m.starts_at<%s AND m.ends_at>%s
                AND (r.sender_id=ANY(%s) OR r.recipient_id=ANY(%s)) LIMIT 1""",
                (
                    meeting_id,
                    row["ends_at"],
                    row["starts_at"],
                    [record["sender_id"], record["recipient_id"]],
                    [record["sender_id"], record["recipient_id"]],
                ),
            ).fetchone()
            if conflict:
                return (
                    jsonify(
                        error="One of you already has an accepted meeting at that time."
                    ),
                    409,
                )
        if row["status"] != status:
            db.execute(
                "UPDATE advice_meetings SET status=%s WHERE id=%s", (status, meeting_id)
            )
            peer = (
                record["recipient_id"]
                if user == record["sender_id"]
                else record["sender_id"]
            )
            notify(
                db,
                peer,
                user,
                record["id"],
                "meeting",
                f"meeting:{meeting_id}:{status}",
            )
        return jsonify(status=status)

    @api.get("/api/requests/<int:request_id>/meetings/<int:meeting_id>/calendar.ics")
    @participant
    def export(db, user, record, meeting_id):
        row = db.execute(
            "SELECT * FROM advice_meetings WHERE id=%s AND request_id=%s AND status='accepted'",
            (meeting_id, record["id"]),
        ).fetchone()
        if not row:
            return jsonify(error="Accepted meeting not found."), 404
        stamp = lambda dt: dt.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        lines = [
            "BEGIN:VCALENDAR",
            "VERSION:2.0",
            "PRODID:-//PackConnect//Advice meetings//EN",
            "BEGIN:VEVENT",
            f"UID:meeting-{meeting_id}@packconnect",
            f"DTSTAMP:{stamp(datetime.now(timezone.utc))}",
            f'DTSTART:{stamp(row["starts_at"])}',
            f'DTEND:{stamp(row["ends_at"])}',
            "SUMMARY:"
            + calendar_escape("PackConnect advice: " + record["course_code"]),
            "LOCATION:" + calendar_escape(row["location"]),
            "END:VEVENT",
            "END:VCALENDAR",
        ]
        # Fold UTF-8 content lines at 75 octets, per iCalendar.
        folded = []
        for line in lines:
            part = ""
            for char in line:
                if len((part + char).encode("utf-8")) > 75:
                    folded.append(part)
                    part = " "
                part += char
            folded.append(part)
        return Response(
            "\r\n".join(folded) + "\r\n",
            mimetype="text/calendar",
            headers={
                "Content-Disposition": f'attachment; filename="packconnect-meeting-{meeting_id}.ics"'
            },
        )

    return api
