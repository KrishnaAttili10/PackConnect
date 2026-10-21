import tempfile
import unittest
from pathlib import Path

import app as portal


class AuthenticationTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.original_path = portal.DB_PATH
        portal.DB_PATH = Path(self.directory.name) / "auth.db"
        portal.initialize_database()
        self.client = portal.app.test_client()
        self.credentials = {"email": "casey@example.edu", "password": "a long test password"}
        response = self.client.post("/api/auth/register", json={
            **self.credentials, "name": "Casey", "program": "Computer Science",
            "year": "First Year",
        })
        self.student_id = response.get_json()["student"]["id"]

    def tearDown(self):
        portal.DB_PATH = self.original_path
        self.directory.cleanup()

    def test_login_restores_session_and_logout_clears_it(self):
        self.assertEqual(self.client.get("/api/auth/me").status_code, 401)
        response = self.client.post("/api/auth/login", json={
            **self.credentials, "email": " CASEY@EXAMPLE.EDU ",
        })
        self.assertEqual(response.status_code, 200)
        student = response.get_json()["student"]
        self.assertEqual(student["id"], self.student_id)
        self.assertNotIn("email", student)
        self.assertNotIn("password_hash", student)
        self.assertIn("HttpOnly", response.headers["Set-Cookie"])
        self.assertIn("SameSite=Lax", response.headers["Set-Cookie"])
        self.assertEqual(self.client.get("/api/auth/me").get_json()["student"]["id"], self.student_id)
        self.assertEqual(self.client.post("/api/auth/logout").status_code, 200)
        self.assertEqual(self.client.get("/api/auth/me").status_code, 401)

    def test_wrong_password_and_unknown_email_do_not_authenticate(self):
        for payload in [
            {**self.credentials, "password": "incorrect password"},
            {**self.credentials, "email": "unknown@example.edu"},
        ]:
            with self.subTest(payload=payload):
                response = self.client.post("/api/auth/login", json=payload)
                self.assertEqual(response.status_code, 401)
                self.assertEqual(response.get_json()["error"], "Email or password is incorrect.")
                self.assertEqual(self.client.get("/api/auth/me").status_code, 401)

    def test_invalid_login_payloads(self):
        for payload in [None, [], {}, {"email": [], "password": 123},
                        {**self.credentials, "password": "x" * 129}]:
            with self.subTest(payload=payload):
                self.assertEqual(self.client.post("/api/auth/login", json=payload).status_code, 400)

    def test_separate_browser_does_not_share_session(self):
        self.client.post("/api/auth/login", json=self.credentials)
        other_client = portal.app.test_client()
        self.assertEqual(other_client.get("/api/auth/me").status_code, 401)

    def test_deleted_profile_invalidates_session(self):
        self.client.post("/api/auth/login", json=self.credentials)
        with portal.get_db() as db:
            db.execute("DELETE FROM students WHERE id = ?", (self.student_id,))
        self.assertEqual(self.client.get("/api/auth/me").status_code, 401)


if __name__ == "__main__":
    unittest.main()
