"""Supabase identity integration using isolated SQL fixtures and a mocked Auth API."""

from types import SimpleNamespace
from unittest.mock import Mock, patch
from uuid import uuid4

import httpx
from supabase_auth.errors import AuthApiError

import app as portal
from postgres_test_support import PostgresTestCase


class SupabaseAuthenticationTests(PostgresTestCase):
    def setUp(self):
        super().setUp()
        self.client = portal.app.test_client()
        self.auth_id = str(uuid4())
        self.email = f"advisor-{self.auth_id}@example.test"
        self.credentials = {"email": self.email, "password": "a long test password"}
        with portal.get_db() as db:
            db.execute("INSERT INTO auth.users (id, email, email_confirmed_at) VALUES (%s, %s, now())",
                       (self.auth_id, self.email))
            self.student_id = db.execute("""
                INSERT INTO students (auth_user_id, name, program, year, willing_to_advise)
                VALUES (%s, 'Supabase Advisor', 'Computer Science', 'First Year', true) RETURNING id
            """, (self.auth_id,)).fetchone()["id"]
            db.execute("INSERT INTO completed_courses (student_id, course_code) VALUES (%s, 'CSC 510')",
                       (self.student_id,))
        self.addCleanup(self.remove_auth_user)
        self.user = SimpleNamespace(id=self.auth_id, email=self.email, email_confirmed_at="2026-01-01")
        self.provider = Mock()
        self.provider.auth.sign_in_with_password.return_value = SimpleNamespace(user=self.user)
        self.factory = self.enterContext(patch.object(portal, "create_client", return_value=self.provider))
        self.enterContext(patch.object(portal, "SUPABASE_URL", "https://auth.example.test"))
        self.enterContext(patch.object(portal, "SUPABASE_SECRET_KEY", "test-server-key"))

    def remove_auth_user(self):
        with portal.get_db() as db:
            db.execute("UPDATE students SET auth_user_id = NULL WHERE auth_user_id = %s", (self.auth_id,))
            db.execute("DELETE FROM auth.users WHERE id = %s", (self.auth_id,))

    def login(self):
        response = self.client.post("/api/auth/login", json=self.credentials)
        self.assertEqual(response.status_code, 200, response.get_json())
        return response

    def test_login_preserves_profile_and_uses_isolated_provider_client(self):
        response = self.login()
        self.assertEqual(response.get_json()["student"]["id"], self.student_id)
        self.assertTrue(response.get_json()["student"]["can_receive_requests"])
        self.assertNotIn("email", response.get_json()["student"])
        self.provider.auth.sign_in_with_password.assert_called_once_with(self.credentials)
        options = self.factory.call_args.kwargs["options"]
        self.assertFalse(options.persist_session)
        self.assertFalse(options.auto_refresh_token)
        self.provider.auth.close.assert_called_once()
        with self.client.session_transaction() as session:
            self.assertEqual(session["auth_user_id"], self.auth_id)
            self.assertNotIn("access_token", session)
            self.assertNotIn("refresh_token", session)
        with portal.get_db() as db:
            self.assertEqual(db.execute("SELECT count(*) AS count FROM students").fetchone()["count"], 5)
            self.assertEqual(db.execute("SELECT count(*) AS count FROM accounts").fetchone()["count"], 0)
        self.assertEqual(self.client.get("/api/auth/me").get_json()["student"]["id"], self.student_id)
        self.assertEqual(portal.app.test_client().get("/api/requests").status_code, 401)
        self.client.post("/api/auth/logout")
        self.assertEqual(self.client.get("/api/requests").status_code, 401)

    def test_confirmed_linked_profile_is_discoverable_and_can_receive_request_before_login(self):
        peers = self.client.get("/api/students/search?course=CSC%20510").get_json()["students"]
        self.assertEqual([peer["id"] for peer in peers], [self.student_id])
        self.assertTrue(self.client.get(f"/api/students/{self.student_id}").get_json()["student"]["can_receive_requests"])
        # A local-account sender can contact the Supabase advisor before their first app login.
        sender = portal.app.test_client()
        credentials = {"email": "sender@example.test", "password": "a long test password"}
        sender.post("/api/auth/register", json={**credentials, "name": "Sender", "program": "CS", "year": "1"})
        self.assertEqual(sender.post("/api/auth/login", json=credentials).status_code, 200)
        self.factory.assert_not_called()
        response = sender.post("/api/requests", json={
            "recipient_id": self.student_id, "course_code": "CSC 510",
            "advice_topic": "Projects", "message": "How should I prepare?",
        })
        self.assertEqual(response.status_code, 201, response.get_json())
        request_id = response.get_json()["request"]["id"]
        self.login()
        inbox = self.client.get("/api/requests").get_json()["requests"]
        self.assertEqual([item["id"] for item in inbox], [request_id])
        self.assertEqual(self.client.patch(f"/api/requests/{request_id}", json={"status": "accepted"}).status_code, 200)
        chat = self.client.post(f"/api/requests/{request_id}/messages", json={"body": "Happy to help!"})
        self.assertEqual(chat.status_code, 201, chat.get_json())
        self.assertEqual(chat.get_json()["message"]["sender_id"], self.student_id)
        self.assertEqual(sender.get(f"/api/requests/{request_id}/messages").get_json()["messages"][0]["body"], "Happy to help!")
        self.assertEqual(self.client.get("/api/notifications").status_code, 200)
        other = portal.app.test_client()
        self.assertEqual(other.get(f"/api/requests/{request_id}/messages").status_code, 401)

    def test_supabase_student_can_send_requests_as_their_existing_profile(self):
        peer = portal.app.test_client()
        response = peer.post("/api/auth/register", json={
            "name": "Local Advisor", "email": "local-advisor@example.test",
            "password": "a long test password", "program": "CS", "year": "1",
            "willing_to_advise": True,
        })
        peer_id = response.get_json()["student"]["id"]
        self.login()
        response = self.client.post("/api/requests", json={
            "recipient_id": peer_id, "course_code": "CSC 510",
            "advice_topic": "Projects", "message": "Can you help?",
        })
        self.assertEqual(response.status_code, 201, response.get_json())
        self.assertEqual(response.get_json()["request"]["sender_id"], self.student_id)

    def test_wrong_provider_password_does_not_create_session(self):
        self.provider.auth.sign_in_with_password.side_effect = AuthApiError("Invalid credentials", 400, "invalid_credentials")
        self.assertEqual(self.client.post("/api/auth/login", json=self.credentials).status_code, 401)
        self.assertEqual(self.client.get("/api/auth/me").status_code, 401)

    def test_provider_outage_does_not_create_session_or_leak_details(self):
        self.provider.auth.sign_in_with_password.side_effect = httpx.ConnectError("private provider details")
        response = self.client.post("/api/auth/login", json=self.credentials)
        self.assertEqual(response.status_code, 503)
        self.assertNotIn("private", response.get_json()["error"])
        self.assertEqual(self.client.get("/api/requests").status_code, 401)

    def test_name_and_email_cannot_link_a_different_provider_identity(self):
        self.user.id = str(uuid4())
        response = self.client.post("/api/auth/login", json=self.credentials)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.client.get("/api/requests").status_code, 401)

    def test_unconfirmed_auth_identity_cannot_login_or_receive_requests(self):
        with portal.get_db() as db:
            db.execute("UPDATE auth.users SET email_confirmed_at = NULL WHERE id = %s", (self.auth_id,))
        self.user.email_confirmed_at = None
        self.assertEqual(self.client.post("/api/auth/login", json=self.credentials).status_code, 401)
        self.assertEqual(self.client.get("/api/students/search?course=CSC%20510").get_json()["students"], [])
        self.assertFalse(self.client.get(f"/api/students/{self.student_id}").get_json()["student"]["can_receive_requests"])

    def test_removing_auth_link_invalidates_existing_session(self):
        self.login()
        with portal.get_db() as db:
            db.execute("UPDATE students SET auth_user_id = NULL WHERE id = %s", (self.student_id,))
        self.assertEqual(self.client.get("/api/requests").status_code, 401)
        self.assertEqual(self.client.get("/api/auth/me").status_code, 401)

    def test_supabase_student_can_edit_only_their_own_profile(self):
        self.login()
        payload = {"name": "Updated Advisor", "program": "CS", "year": "2", "completed_courses": ["CSC 510"]}
        self.assertEqual(self.client.put(f"/api/students/{self.student_id}", json=payload).status_code, 200)
        self.assertEqual(self.client.put("/api/students/1", json=payload).status_code, 403)

    def test_registration_does_not_create_duplicate_local_account(self):
        response = self.client.post("/api/auth/register", json={
            **self.credentials, "name": "Duplicate Advisor", "program": "CS", "year": "1",
        })
        self.assertEqual(response.status_code, 409)
        with portal.get_db() as db:
            self.assertEqual(db.execute("SELECT count(*) AS count FROM students").fetchone()["count"], 5)
