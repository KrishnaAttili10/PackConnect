"""Advisor settings and shared, database-time availability calculations."""

from datetime import date
from identity import registered_student_sql


def availability_payload(data):
    fields = {}
    if "max_open_requests" in data:
        limit = data["max_open_requests"]
        if limit is not None and (type(limit) is not int or not 1 <= limit <= 100):
            raise ValueError("Maximum open requests must be a whole number from 1 to 100, or null for no limit.")
        fields["max_open_requests"] = limit
    if "pause_until" in data:
        value = data["pause_until"]
        if value is None:
            fields["pause_until"] = None
        else:
            try:
                parsed = date.fromisoformat(value)
                if parsed.isoformat() != value:
                    raise ValueError()
            except (ValueError, TypeError):
                raise ValueError("Pause until must be a date in YYYY-MM-DD format, or null.") from None
            fields["pause_until"] = parsed
    return fields


def workload_join():
    return """LEFT JOIN LATERAL (
        SELECT COUNT(*) AS open_request_count FROM advice_requests
        WHERE recipient_id = s.id AND status IN ('pending', 'accepted')
    ) w ON true"""


def availability_status_sql():
    return f"""CASE
        WHEN NOT {registered_student_sql()} THEN 'unregistered'
        WHEN NOT s.willing_to_advise THEN 'not_advising'
        WHEN s.pause_until > (CURRENT_TIMESTAMP AT TIME ZONE 'America/New_York')::date THEN 'paused'
        WHEN s.max_open_requests IS NOT NULL AND w.open_request_count >= s.max_open_requests THEN 'at_capacity'
        ELSE 'available' END"""


def availability_columns():
    return f"""s.max_open_requests, s.pause_until, w.open_request_count,
        ({availability_status_sql()}) AS availability_status,
        ({availability_status_sql()} = 'available') AS accepting_requests"""


def advisor_availability(db, student_id):
    """Call after locking the advisor row when enforcing a capacity mutation."""
    return db.execute(f"""
        SELECT {availability_columns()} FROM students s {workload_join()}
        WHERE s.id = %s
    """, (student_id,)).fetchone()
