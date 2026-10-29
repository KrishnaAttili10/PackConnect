"""Recognize existing Flask accounts and confirmed Supabase-linked profiles."""


def registered_student_sql(alias="s"):
    # Callers supply a fixed SQL alias, never user input.
    return f"""(
        EXISTS (SELECT 1 FROM accounts a WHERE a.student_id = {alias}.id)
        OR EXISTS (
            SELECT 1 FROM auth.users u
            WHERE u.id = {alias}.auth_user_id AND u.email_confirmed_at IS NOT NULL
        )
    )"""


def session_student_id(db, session):
    student_id = session.get("student_id")
    if not student_id:
        return None
    if session.get("auth_user_id"):
        row = db.execute("""
            SELECT s.id, s.session_version FROM students s JOIN auth.users u ON u.id = s.auth_user_id
            WHERE s.id = %s AND u.id = %s AND u.email_confirmed_at IS NOT NULL
        """, (student_id, session["auth_user_id"])).fetchone()
    else:
        row = db.execute("SELECT s.id, s.session_version FROM accounts a JOIN students s ON s.id = a.student_id WHERE s.id = %s",
                         (student_id,)).fetchone()
    return row["id"] if row and row["session_version"] == session.get("auth_version", 0) else None
