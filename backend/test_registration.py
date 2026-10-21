import unittest

from werkzeug.security import check_password_hash
import app as portal
from postgres_test_support import PostgresTestCase


class RegistrationTests(PostgresTestCase):
    def setUp(self):
        super().setUp()
        self.client = portal.app.test_client()
        self.payload = dict(name=" Casey Smith ", email=" Casey@Example.edu ",
                            password="a long test password", program="MS Computer Science",
                            year="First Year", willing_to_advise=True,
                            completed_courses=[" csc 510 ", "CSC 510", "CSC 540"])

    def test_registration_creates_searchable_profile_and_hashes_password(self):
        response = self.client.post("/api/auth/register", json=self.payload)
        self.assertEqual(response.status_code, 201)
        student = response.get_json()["student"]
        self.assertEqual(student["name"], "Casey Smith")
        self.assertEqual(student["completed_courses"], ["CSC 510", "CSC 540"])
        with portal.get_db() as db:
            account = db.execute("SELECT * FROM accounts").fetchone()
        self.assertEqual(account["email"], "casey@example.edu")
        self.assertNotEqual(account["password_hash"], self.payload["password"])
        self.assertTrue(check_password_hash(account["password_hash"], self.payload["password"]))
        results = self.client.get("/api/students/search?course=CSC%20510").get_json()["students"]
        self.assertIn(student["id"], [row["id"] for row in results])
        profile = self.client.get(f"/api/students/{student['id']}").get_json()["student"]
        self.assertEqual(profile["completed_courses"], ["CSC 510", "CSC 540"])
        self.assertEqual(profile["current_courses"], [])
        for field in ("name", "program", "year", "willing_to_advise"):
            self.assertEqual(profile[field], student[field])
        for private_field in ["email", "password", "password_hash", "auth_user_id"]:
            self.assertNotIn(private_field, student)
            self.assertNotIn(private_field, profile)

    def test_duplicate_email_rolls_back_entire_registration(self):
        self.client.post("/api/auth/register", json=self.payload)
        self.payload["email"] = "CASEY@EXAMPLE.EDU"
        response = self.client.post("/api/auth/register", json=self.payload)
        self.assertEqual(response.status_code, 409)
        with portal.get_db() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM accounts").fetchone()["count"], 1)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM students").fetchone()["count"], 5)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM completed_courses WHERE student_id > 4").fetchone()["count"], 2)

    def test_invalid_registration_does_not_create_records(self):
        invalid = [None, [], {}, *[{**self.payload, key: value} for key, value in [
            ("name", " "), ("name", 123), ("email", "bad@email"),
            ("password", "short"), ("password", "x" * 129), ("password", None),
            ("program", ""), ("year", ""), ("bio", "x" * 2001),
            ("willing_to_advise", "false"), ("completed_courses", "CSC 510"),
            ("completed_courses", [123]), ("completed_courses", [" "]),
            ("completed_courses", ["CSC 510"] * 51),
        ]]]
        for payload in invalid:
            with self.subTest(payload=payload):
                self.assertEqual(self.client.post("/api/auth/register", json=payload).status_code, 400)
        with portal.get_db() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM accounts").fetchone()["count"], 0)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM students").fetchone()["count"], 4)

    def test_advising_is_opt_in_and_database_initialization_preserves_accounts(self):
        self.payload.pop("willing_to_advise")
        response = self.client.post("/api/auth/register", json=self.payload)
        student_id = response.get_json()["student"]["id"]
        portal.initialize_database()
        results = self.client.get("/api/students/search?course=CSC%20510").get_json()["students"]
        self.assertNotIn(student_id, [row["id"] for row in results])
        with portal.get_db() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM accounts").fetchone()["count"], 1)

    def test_each_required_registration_field_is_required(self):
        for field in ("name", "email", "password", "program", "year"):
            for value in ("missing", "", "   "):
                with self.subTest(field=field, value=value):
                    payload = {**self.payload, field: value}
                    if value == "missing":
                        payload.pop(field)
                    response = self.client.post("/api/auth/register", json=payload)
                    self.assertEqual(response.status_code, 400)
                    self.assertIn("error", response.get_json())
        with portal.get_db() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM accounts").fetchone()["count"], 0)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM students").fetchone()["count"], 4)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM completed_courses").fetchone()["count"], 7)

    def test_malformed_registration_bodies_do_not_create_profiles_or_courses(self):
        for body, content_type in [("", "application/json"), ('{"name":', "application/json"),
                                   ("null", "application/json"), ('"text"', "application/json"),
                                   ("42", "application/json"), ("[]", "application/json"),
                                   ('{"name":"Owner"}', "text/plain")]:
            with self.subTest(body=body, content_type=content_type):
                response = self.client.post("/api/auth/register", data=body, content_type=content_type)
                self.assertEqual(response.status_code, 400)
                self.assertIn("error", response.get_json())
        with portal.get_db() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM accounts").fetchone()["count"], 0)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM students").fetchone()["count"], 4)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM completed_courses").fetchone()["count"], 7)


if __name__ == "__main__":
    unittest.main()
