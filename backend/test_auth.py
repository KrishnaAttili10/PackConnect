
import unittest
import app as portal
from testing_supabase import FakeSupabase, build_test_app


class AuthenticationTests(unittest.TestCase):
    def setUp(self):
        self.db = FakeSupabase()
        self.app = build_test_app(portal, self.db)
        self.client = self.app.test_client()
        self.student_id, self.user_id = self.db.seed_user("Test Student", "student@example.edu")

    def test_login_restores_session_and_logout_clears_it(self):
        response = self.client.post("/api/auth/login", json={
            "email": " STUDENT@EXAMPLE.EDU ", "password": "a long test password"
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["student"]["id"], self.student_id)
        self.assertEqual(self.client.get("/api/auth/me").status_code, 200)
        self.assertEqual(self.client.post("/api/auth/logout").status_code, 200)
        self.assertEqual(self.client.get("/api/auth/me").status_code, 401)

    def test_wrong_password_and_unknown_email_do_not_authenticate(self):
        for email, password in [
            ("student@example.edu", "wrong password"),
            ("unknown@example.edu", "a long test password"),
        ]:
            response = self.client.post("/api/auth/login", json={"email": email, "password": password})
            self.assertEqual(response.status_code, 401)
            self.assertEqual(self.client.get("/api/auth/me").status_code, 401)

    def test_invalid_login_payloads(self):
        for payload in [None, [], {}, {"email": "student@example.edu"},
                        {"email": "", "password": "long enough password"},
                        {"email": "bad", "password": "x" * 129}]:
            with self.subTest(payload=payload):
                response = self.client.post("/api/auth/login", json=payload)
                self.assertEqual(response.status_code, 400)

    def test_separate_browser_does_not_share_session(self):
        response = self.client.post("/api/auth/login", json={
            "email": "student@example.edu", "password": "a long test password"
        })
        self.assertEqual(response.status_code, 200)
        other_browser = self.app.test_client()
        self.assertEqual(other_browser.get("/api/auth/me").status_code, 401)

    def test_deleted_profile_invalidates_session(self):
        self.client.post("/api/auth/login", json={
            "email": "student@example.edu", "password": "a long test password"
        })
        self.db.table("students").delete().eq("id", self.student_id).execute()
        response = self.client.get("/api/auth/me")
        self.assertEqual(response.status_code, 401)


if __name__ == "__main__":
    unittest.main()
