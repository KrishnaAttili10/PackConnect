"""Single-use password recovery links delivered through configured SMTP."""

import hashlib
import os
import re
import secrets
import smtplib
import ssl
from email.message import EmailMessage
from urllib.parse import urlparse

from flask import Blueprint, current_app, jsonify, request
from supabase import create_client
from supabase.lib.client_options import SyncClientOptions
from werkzeug.security import generate_password_hash
from lifecycle import lock_students


def send_recovery_email(email, link):
    message = EmailMessage()
    message["Subject"] = "Reset your PackConnect password"
    message["From"] = os.environ["SMTP_FROM"]
    message["To"] = email
    message.set_content(
        f"Use this single-use link within 30 minutes to reset your PackConnect password:\n\n{link}\n\nIf you did not request this, you can ignore this email."
    )
    implicit = os.getenv("SMTP_SSL", "false").lower() == "true"
    transport = smtplib.SMTP_SSL if implicit else smtplib.SMTP
    with transport(
        os.environ["SMTP_HOST"],
        int(os.getenv("SMTP_PORT", "465" if implicit else "587")),
        timeout=15,
        **({"context": ssl.create_default_context()} if implicit else {}),
    ) as server:
        if not implicit:
            server.starttls(context=ssl.create_default_context())
        if os.getenv("SMTP_USERNAME"):
            server.login(os.environ["SMTP_USERNAME"], os.environ["SMTP_PASSWORD"])
        server.send_message(message)


def update_provider_password(auth_id, password):
    if not os.getenv("SUPABASE_URL") or not os.getenv("SUPABASE_SECRET_KEY"):
        raise RuntimeError("Provider password recovery is not configured.")
    client = create_client(
        os.environ["SUPABASE_URL"],
        os.environ["SUPABASE_SECRET_KEY"],
        options=SyncClientOptions(persist_session=False, auto_refresh_token=False),
    )
    try:
        client.auth.admin.update_user_by_id(str(auth_id), {"password": password})
    finally:
        client.auth.close()


def limited(db, scope, maximum):
    key = hashlib.sha256(
        f'{scope}:{request.remote_addr or "unknown"}'.encode()
    ).hexdigest()
    row = db.execute(
        """INSERT INTO recovery_limits(key_hash) VALUES(%s)
        ON CONFLICT(key_hash) DO UPDATE SET
        attempts=CASE WHEN recovery_limits.window_start<now()-interval '1 hour' THEN 1 ELSE recovery_limits.attempts+1 END,
        window_start=CASE WHEN recovery_limits.window_start<now()-interval '1 hour' THEN now() ELSE recovery_limits.window_start END
        RETURNING attempts""",
        (key,),
    ).fetchone()
    return row["attempts"] > maximum


def create_recovery_blueprint(get_db):
    api = Blueprint("recovery", __name__)

    @api.post("/api/auth/forgot-password")
    def forgot():
        data = request.get_json(silent=True)
        email = data.get("email") if isinstance(data, dict) else None
        if (
            not isinstance(email, str)
            or len(email.strip()) > 254
            or not re.fullmatch(r"[^\s@]+@[^\s@.]+(?:\.[^\s@.]+)+", email.strip())
        ):
            return jsonify(error="Enter your email address."), 400
        base = os.getenv("PUBLIC_APP_URL", "").rstrip("/")
        parsed = urlparse(base)
        if (
            not os.getenv("SMTP_HOST")
            or not os.getenv("SMTP_FROM")
            or parsed.scheme not in ("https", "http")
            or not parsed.netloc
            or parsed.fragment
            or parsed.query
        ):
            return (
                jsonify(
                    error="Password recovery email is not configured yet. Contact the project team."
                ),
                503,
            )
        token = secrets.token_urlsafe(32)
        digest = hashlib.sha256(token.encode()).hexdigest()
        eligible = None
        with get_db() as db:
            if limited(db, "request", 5):
                return (
                    jsonify(
                        error="Too many recovery attempts. Please try again in an hour."
                    ),
                    429,
                )
            eligible = db.execute(
                """SELECT s.id,s.auth_user_id,a.email AS local_email FROM students s
                LEFT JOIN accounts a ON a.student_id=s.id LEFT JOIN auth.users u ON u.id=s.auth_user_id
                WHERE lower(a.email)=%s OR (a.id IS NULL AND lower(u.email)=%s AND u.email_confirmed_at IS NOT NULL)
                LIMIT 1 FOR NO KEY UPDATE OF s""",
                (email.strip().lower(), email.strip().lower()),
            ).fetchone()
            if eligible:
                count = db.execute(
                    "SELECT count(*) AS n FROM password_reset_tokens WHERE student_id=%s AND created_at>now()-interval '1 hour'",
                    (eligible["id"],),
                ).fetchone()["n"]
                if count >= 3:
                    eligible = None
            if eligible:
                db.execute(
                    "UPDATE password_reset_tokens SET used_at=now() WHERE student_id=%s AND used_at IS NULL",
                    (eligible["id"],),
                )
                db.execute(
                    "INSERT INTO password_reset_tokens(token_hash,student_id,expires_at) VALUES(%s,%s,now()+interval '30 minutes')",
                    (digest, eligible["id"]),
                )
        if eligible:
            try:
                send_recovery_email(
                    email.strip().lower(), base + "/#/reset-password?token=" + token
                )
            except Exception:
                with get_db() as db:
                    db.execute(
                        "UPDATE password_reset_tokens SET used_at=now() WHERE token_hash=%s",
                        (digest,),
                    )
                current_app.logger.warning(
                    "Recovery email delivery failed; token invalidated."
                )
                # Same response for existing/unknown accounts avoids account disclosure.
        return jsonify(
            message="If an eligible account exists, a recovery email will be sent. Check your inbox and spam folder."
        )

    @api.post("/api/auth/reset-password")
    def reset():
        data = request.get_json(silent=True)
        token = data.get("token") if isinstance(data, dict) else None
        password = data.get("password") if isinstance(data, dict) else None
        if (
            not isinstance(token, str)
            or not 32 <= len(token) <= 128
            or not isinstance(password, str)
            or not 12 <= len(password) <= 128
        ):
            return (
                jsonify(
                    error="Use a valid recovery link and a password of 12–128 characters."
                ),
                400,
            )
        digest = hashlib.sha256(token.encode()).hexdigest()
        password_hash = generate_password_hash(password)
        with get_db() as db:
            if limited(db, "confirm", 20):
                return (
                    jsonify(
                        error="Too many recovery attempts. Please try again in an hour."
                    ),
                    429,
                )
            row = db.execute(
                """SELECT t.student_id,s.auth_user_id FROM password_reset_tokens t JOIN students s ON s.id=t.student_id
                WHERE t.token_hash=%s AND t.used_at IS NULL AND t.expires_at>now()""",
                (digest,),
            ).fetchone()
            if not row:
                return (
                    jsonify(
                        error="This recovery link is invalid or expired. Request a new link."
                    ),
                    400,
                )
            lock_students(db, row["student_id"])
            if not db.execute(
                "SELECT 1 FROM password_reset_tokens WHERE token_hash=%s AND used_at IS NULL AND expires_at>now() FOR UPDATE",
                (digest,),
            ).fetchone():
                return (
                    jsonify(
                        error="This recovery link is invalid or expired. Request a new link."
                    ),
                    400,
                )
            account = db.execute(
                "SELECT id FROM accounts WHERE student_id=%s", (row["student_id"],)
            ).fetchone()
            if account:
                db.execute(
                    "UPDATE accounts SET password_hash=%s WHERE student_id=%s",
                    (password_hash, row["student_id"]),
                )
            elif row["auth_user_id"]:
                try:
                    update_provider_password(row["auth_user_id"], password)
                except Exception:
                    current_app.logger.warning("Provider password recovery failed.")
                    return (
                        jsonify(
                            error="Could not update your password. Please try again or contact the project team."
                        ),
                        503,
                    )
            else:
                return jsonify(error="This account cannot use password recovery."), 400
            db.execute(
                "UPDATE students SET session_version=session_version+1 WHERE id=%s",
                (row["student_id"],),
            )
            db.execute(
                "UPDATE password_reset_tokens SET used_at=now() WHERE student_id=%s AND used_at IS NULL",
                (row["student_id"],),
            )
        return jsonify(message="Password updated. Sign in with your new password.")

    return api
