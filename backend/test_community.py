"""Lifecycle, inbox, contact controls, moderation, recovery, and scheduling."""

from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4
import os
from unittest.mock import patch

import app as portal
from lifecycle import expire_requests
from postgres_test_support import PostgresTestCase


class CommunityTests(PostgresTestCase):
    @classmethod
    def setUpClass(cls):
        cls.password = "a long test password"
        cls.hashed = portal.generate_password_hash(cls.password)

    def setUp(self):
        super().setUp()
        self.ids = []
        self.clients = []
        with portal.get_db() as db:
            for name in ("Alice", "Bob", "Carol"):
                student = db.execute(
                    "INSERT INTO students(name,program,year,willing_to_advise) VALUES(%s,'CS','1',true) RETURNING id",
                    (name,),
                ).fetchone()["id"]
                db.execute(
                    "INSERT INTO accounts(student_id,email,password_hash) VALUES(%s,%s,%s)",
                    (student, name.lower() + "@example.test", self.hashed),
                )
                self.ids.append(student)
        for student in self.ids:
            client = portal.app.test_client()
            with client.session_transaction() as sess:
                sess["student_id"] = student
            self.clients.append(client)
        self.alice, self.bob, self.carol = self.clients
        self.payload = {
            "recipient_id": self.ids[1],
            "course_code": "CSC 510",
            "advice_topic": "Projects",
            "message": "Help please",
        }

    def connect(self, accepted=False):
        response = self.alice.post("/api/requests", json=self.payload)
        self.assertEqual(response.status_code, 201, response.get_json())
        request_id = response.get_json()["request"]["id"]
        if accepted:
            self.bob.patch(f"/api/requests/{request_id}", json={"status": "accepted"})
        return request_id

    def meeting(self, request_id, start=None):
        start = start or datetime.now(timezone.utc) + timedelta(days=1)
        return self.alice.post(
            f"/api/requests/{request_id}/meetings",
            json={
                "starts_at": start.isoformat(),
                "ends_at": (start + timedelta(minutes=30)).isoformat(),
                "location": "Library, room 2",
            },
        )

    def test_sender_cancel_is_idempotent_and_frees_capacity(self):
        rid = self.connect()
        url = f"/api/requests/{rid}"
        self.assertEqual(
            self.bob.patch(url, json={"status": "cancelled"}).status_code, 403
        )
        self.assertEqual(
            self.carol.patch(url, json={"status": "cancelled"}).status_code, 404
        )
        for _ in range(2):
            self.assertEqual(
                self.alice.patch(url, json={"status": "cancelled"}).status_code, 200
            )
        feed = self.bob.get("/api/notifications").get_json()["notifications"]
        self.assertEqual(sum(n["kind"] == "cancelled" for n in feed), 1)
        self.assertEqual(
            self.alice.post("/api/requests", json=self.payload).status_code, 201
        )

    def test_cannot_cancel_accepted_request(self):
        rid = self.connect(True)
        self.assertEqual(
            self.alice.patch(
                f"/api/requests/{rid}", json={"status": "cancelled"}
            ).status_code,
            409,
        )

    def test_expiration_notifies_both_once_and_allows_same_pair_again(self):
        rid = self.connect()
        with portal.get_db() as db:
            db.execute(
                "UPDATE advice_requests SET expires_at=now()-interval '1 second' WHERE id=%s",
                (rid,),
            )
        rows = self.alice.get("/api/requests").get_json()["requests"]
        self.assertEqual(rows[0]["status"], "expired")
        with portal.get_db() as db:
            self.assertEqual(expire_requests(db), 0)
        for client in (self.alice, self.bob):
            self.assertEqual(
                sum(
                    n["kind"] == "expired"
                    for n in client.get("/api/notifications").get_json()[
                        "notifications"
                    ]
                ),
                1,
            )
        self.assertEqual(
            self.alice.post("/api/requests", json=self.payload).status_code, 201
        )

    def test_accepting_expired_request_is_rejected(self):
        rid = self.connect()
        with portal.get_db() as db:
            db.execute(
                "UPDATE advice_requests SET expires_at=now()-interval '1 second' WHERE id=%s",
                (rid,),
            )
        self.assertEqual(
            self.bob.patch(
                f"/api/requests/{rid}", json={"status": "accepted"}
            ).status_code,
            409,
        )

    def test_inbox_preview_unread_and_pagination_cursor(self):
        rid = self.connect(True)
        self.alice.post(
            f"/api/requests/{rid}/messages", json={"body": "Private advice"}
        )
        inbox = self.bob.get("/api/conversations").get_json()["conversations"]
        self.assertEqual(
            (inbox[0]["latest_message"], inbox[0]["unread_count"]),
            ("Private advice", 1),
        )
        self.assertEqual(
            self.carol.get("/api/conversations").get_json()["conversations"], []
        )
        self.bob.get(f"/api/requests/{rid}/messages?after_id=999999")
        self.assertEqual(
            self.bob.get("/api/conversations").get_json()["conversations"][0][
                "unread_count"
            ],
            1,
        )
        self.bob.get(f"/api/requests/{rid}/messages")
        self.assertEqual(
            self.bob.get("/api/conversations").get_json()["conversations"][0][
                "unread_count"
            ],
            0,
        )

    def test_block_closes_connection_cancels_meeting_and_stops_contact(self):
        rid = self.connect(True)
        meeting = self.meeting(rid).get_json()["meeting"]["id"]
        self.bob.patch(
            f"/api/requests/{rid}/meetings/{meeting}", json={"status": "accepted"}
        )
        self.assertEqual(
            self.bob.post(f"/api/students/{self.ids[0]}/block").status_code, 200
        )
        self.assertEqual(
            self.alice.post("/api/requests", json=self.payload).status_code, 403
        )
        self.assertEqual(
            self.alice.post(
                f"/api/requests/{rid}/messages", json={"body": "Blocked"}
            ).status_code,
            403,
        )
        history = self.alice.get(f"/api/requests/{rid}/messages")
        self.assertEqual(history.status_code, 200)
        self.assertFalse(history.get_json()["request"]["contact_allowed"])
        self.assertEqual(
            self.bob.get("/api/blocks").get_json()["blocks"][0]["id"], self.ids[0]
        )
        self.assertEqual(
            self.bob.get(f"/api/requests/{rid}/meetings").get_json()["meetings"][0][
                "status"
            ],
            "cancelled",
        )
        self.bob.delete(f"/api/students/{self.ids[0]}/block")
        self.assertEqual(
            self.alice.post("/api/requests", json=self.payload).status_code, 201
        )

    def test_report_message_access_and_moderator_authorization(self):
        rid = self.connect(True)
        mid = self.alice.post(
            f"/api/requests/{rid}/messages", json={"body": "Reported message"}
        ).get_json()["message"]["id"]
        url = f"/api/students/{self.ids[0]}/reports"
        self.assertEqual(
            self.carol.post(
                url, json={"reason": "Not shared with me", "message_id": mid}
            ).status_code,
            400,
        )
        report = self.bob.post(
            url, json={"reason": "Concern about this message", "message_id": mid}
        )
        self.assertEqual(report.status_code, 201)
        report_id = report.get_json()["report_id"]
        self.assertEqual(self.bob.get("/api/moderation/reports").status_code, 403)
        with portal.get_db() as db:
            db.execute(
                "INSERT INTO staff_members(student_id) VALUES(%s)", (self.ids[2],)
            )
        rows = self.carol.get("/api/moderation/reports").get_json()["reports"]
        self.assertEqual(rows[0]["message_body"], "Reported message")
        self.assertEqual(
            self.carol.patch(
                f"/api/moderation/reports/{report_id}",
                json={"status": "resolved", "resolution": "Reviewed and addressed"},
            ).status_code,
            200,
        )
        self.assertEqual(
            self.carol.patch(
                f"/api/moderation/reports/{report_id}",
                json={"status": "dismissed", "resolution": "Again"},
            ).status_code,
            404,
        )

    def test_meeting_requires_other_participant_and_exports_calendar(self):
        rid = self.connect(True)
        response = self.meeting(rid)
        self.assertEqual(response.status_code, 201, response.get_json())
        mid = response.get_json()["meeting"]["id"]
        url = f"/api/requests/{rid}/meetings/{mid}"
        self.assertEqual(
            self.alice.patch(url, json={"status": "accepted"}).status_code, 403
        )
        self.assertEqual(
            self.carol.patch(url, json={"status": "accepted"}).status_code, 404
        )
        self.assertEqual(
            self.bob.patch(url, json={"status": "accepted"}).status_code, 200
        )
        calendar = self.bob.get(url + "/calendar.ics")
        self.assertEqual(calendar.status_code, 200)
        self.assertIn("LOCATION:Library\\, room 2", calendar.get_data(as_text=True))
        self.assertIn("DTSTART:", calendar.get_data(as_text=True))
        self.assertEqual(
            self.alice.patch(url, json={"status": "cancelled"}).status_code, 200
        )
        self.assertEqual(self.bob.get(url + "/calendar.ics").status_code, 404)

    def test_meeting_conflicts_and_invalid_times(self):
        rid = self.connect(True)
        start = datetime.now(timezone.utc) + timedelta(days=1)
        first = self.meeting(rid, start).get_json()["meeting"]["id"]
        self.bob.patch(
            f"/api/requests/{rid}/meetings/{first}", json={"status": "accepted"}
        )
        second = self.carol.post(
            "/api/requests", json={**self.payload, "recipient_id": self.ids[0]}
        ).get_json()["request"]["id"]
        self.alice.patch(f"/api/requests/{second}", json={"status": "accepted"})
        proposal = self.carol.post(
            f"/api/requests/{second}/meetings",
            json={
                "starts_at": start.isoformat(),
                "ends_at": (start + timedelta(minutes=30)).isoformat(),
                "location": "Online",
            },
        ).get_json()["meeting"]["id"]
        self.assertEqual(
            self.alice.patch(
                f"/api/requests/{second}/meetings/{proposal}",
                json={"status": "accepted"},
            ).status_code,
            409,
        )
        self.assertEqual(self.meeting(rid, start - timedelta(days=2)).status_code, 400)

    def recovery_link(self):
        config = {
            "SMTP_HOST": "smtp.example.test",
            "SMTP_FROM": "noreply@example.test",
            "PUBLIC_APP_URL": "https://pack.example.test",
        }
        self.enterContext(patch.dict(os.environ, config))
        self.mail = self.enterContext(patch("recovery.send_recovery_email"))
        response = self.alice.post(
            "/api/auth/forgot-password", json={"email": "alice@example.test"}
        )
        self.assertEqual(response.status_code, 200, response.get_json())
        return self.mail.call_args.args[1].split("token=")[1]

    def test_password_reset_single_use_hashing_and_session_invalidation(self):
        token = self.recovery_link()
        with portal.get_db() as db:
            row = db.execute("SELECT token_hash FROM password_reset_tokens").fetchone()
            self.assertNotEqual(row["token_hash"], token)
            self.assertEqual(len(row["token_hash"]), 64)
        new = "a different long password"
        client = portal.app.test_client()
        self.assertEqual(
            client.post(
                "/api/auth/reset-password", json={"token": token, "password": new}
            ).status_code,
            200,
        )
        self.assertEqual(self.alice.get("/api/requests").status_code, 401)
        self.assertEqual(
            client.post(
                "/api/auth/reset-password", json={"token": token, "password": new}
            ).status_code,
            400,
        )
        self.assertEqual(
            client.post(
                "/api/auth/login",
                json={"email": "alice@example.test", "password": self.password},
            ).status_code,
            401,
        )
        self.assertEqual(
            client.post(
                "/api/auth/login", json={"email": "alice@example.test", "password": new}
            ).status_code,
            200,
        )

    def test_expired_recovery_and_unknown_account_response(self):
        token = self.recovery_link()
        known = self.alice.post(
            "/api/auth/forgot-password", json={"email": "alice@example.test"}
        ).get_json()
        unknown = self.alice.post(
            "/api/auth/forgot-password", json={"email": "missing@example.test"}
        ).get_json()
        self.assertEqual(known, unknown)
        with portal.get_db() as db:
            db.execute(
                "UPDATE password_reset_tokens SET expires_at=now()-interval '1 minute'"
            )
        self.assertEqual(
            self.alice.post(
                "/api/auth/reset-password",
                json={"token": token, "password": "a different long password"},
            ).status_code,
            400,
        )

    def test_recovery_without_sender_configuration_is_explicit(self):
        with patch.dict(
            os.environ, {"SMTP_HOST": "", "SMTP_FROM": "", "PUBLIC_APP_URL": ""}
        ):
            self.assertEqual(
                self.alice.post(
                    "/api/auth/forgot-password", json={"email": "alice@example.test"}
                ).status_code,
                503,
            )

    def test_blocked_peers_are_hidden_from_search_in_both_directions(self):
        with portal.get_db() as db:
            for student in self.ids:
                db.execute(
                    "INSERT INTO completed_courses(student_id,course_code) VALUES(%s,'CSC 510')",
                    (student,),
                )
        self.bob.post(f"/api/students/{self.ids[0]}/block")
        for client, hidden in ((self.alice, self.ids[1]), (self.bob, self.ids[0])):
            ids = [
                s["id"]
                for s in client.get(
                    "/api/students/search?course=CSC510&available=false"
                ).get_json()["students"]
            ]
            self.assertNotIn(hidden, ids)
        profile = self.bob.get(f"/api/students/{self.ids[0]}").get_json()["student"]
        self.assertTrue(profile["blocked_by_me"])
        self.assertFalse(profile["contact_allowed"])

    def test_recovery_rate_limit_and_delivery_failure_invalidate_token(self):
        self.recovery_link()
        self.mail.side_effect = RuntimeError("mock transport failure")
        response = self.alice.post(
            "/api/auth/forgot-password", json={"email": "alice@example.test"}
        )
        self.assertEqual(response.status_code, 200)
        with portal.get_db() as db:
            self.assertEqual(
                db.execute(
                    "SELECT count(*) AS n FROM password_reset_tokens WHERE used_at IS NULL"
                ).fetchone()["n"],
                0,
            )
        for _ in range(3):
            self.alice.post(
                "/api/auth/forgot-password", json={"email": "missing@example.test"}
            )
        self.assertEqual(
            self.alice.post(
                "/api/auth/forgot-password", json={"email": "missing@example.test"}
            ).status_code,
            429,
        )

    def test_supabase_recovery_uses_provider_without_creating_local_credentials(self):
        auth_id = str(uuid4())
        with portal.get_db() as db:
            db.execute("DELETE FROM accounts WHERE student_id=%s", (self.ids[0],))
            db.execute(
                "INSERT INTO auth.users(id,email,email_confirmed_at) VALUES(%s,'alice@example.test',now())",
                (auth_id,),
            )
            db.execute(
                "UPDATE students SET auth_user_id=%s WHERE id=%s",
                (auth_id, self.ids[0]),
            )

        def cleanup():
            with portal.get_db() as db:
                db.execute(
                    "UPDATE students SET auth_user_id=NULL WHERE id=%s", (self.ids[0],)
                )
                db.execute("DELETE FROM auth.users WHERE id=%s", (auth_id,))

        self.addCleanup(cleanup)
        token = self.recovery_link()
        with patch("recovery.update_provider_password") as provider:
            response = portal.app.test_client().post(
                "/api/auth/reset-password",
                json={"token": token, "password": "a new provider password"},
            )
        self.assertEqual(response.status_code, 200, response.get_json())
        provider.assert_called_once_with(UUID(auth_id), "a new provider password")
        with portal.get_db() as db:
            self.assertFalse(
                db.execute(
                    "SELECT 1 FROM accounts WHERE student_id=%s", (self.ids[0],)
                ).fetchone()
            )
