"""Request expiration and contact rules shared by app routes and maintenance."""


def blocked(db, first, second):
    return bool(
        db.execute(
            """SELECT 1 FROM student_blocks
        WHERE (blocker_id = %s AND blocked_id = %s) OR (blocker_id = %s AND blocked_id = %s)""",
            (first, second, second, first),
        ).fetchone()
    )


def lock_students(db, *ids):
    # Consistent ordering avoids cross-direction deadlocks. NO KEY UPDATE permits FK checks.
    db.execute(
        "SELECT id FROM students WHERE id = ANY(%s) ORDER BY id FOR NO KEY UPDATE",
        (sorted(set(ids)),),
    ).fetchall()


def notify(db, user_id, actor_id, request_id, kind, event_key):
    db.execute(
        """INSERT INTO notifications(user_id,actor_id,request_id,kind,event_key)
        VALUES (%s,%s,%s,%s,%s) ON CONFLICT(event_key) DO NOTHING""",
        (user_id, actor_id, request_id, kind, event_key),
    )


def expire_requests(db, student_id=None, recipient_id=None):
    conditions = ["status = 'pending'", "expires_at <= CURRENT_TIMESTAMP"]
    params = []
    if student_id is not None:
        conditions.append("(sender_id = %s OR recipient_id = %s)")
        params.extend([student_id, student_id])
    if recipient_id is not None:
        conditions.append("recipient_id = %s")
        params.append(recipient_id)
    where = " AND ".join(conditions)
    advisors = db.execute(
        f"SELECT DISTINCT recipient_id FROM advice_requests WHERE {where} ORDER BY recipient_id",
        params,
    ).fetchall()
    changed = 0
    for advisor in advisors:
        lock_students(db, advisor["recipient_id"])
        rows = db.execute(
            f"""UPDATE advice_requests SET status = 'expired'
            WHERE {where} AND recipient_id = %s RETURNING id,sender_id,recipient_id""",
            (*params, advisor["recipient_id"]),
        ).fetchall()
        for row in rows:
            for user, actor in (
                (row["sender_id"], row["recipient_id"]),
                (row["recipient_id"], row["sender_id"]),
            ):
                notify(
                    db, user, actor, row["id"], "expired", f"expired:{row['id']}:{user}"
                )
        changed += len(rows)
    return changed
