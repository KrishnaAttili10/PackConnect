
import unittest
import app as portal
from testing_supabase import FakeSupabase, build_test_app


class RegistrationTests(unittest.TestCase):
    def setUp(self):
        self.db = FakeSupabase()
        self.app = build_test_app(portal, self.db)
        self.client = self.app.test_client()
        self.payload = dict(
            name=" Casey Smith ", email=" Casey@Example.edu ",
            password="a long test password", program="MS Computer Science",
            year="First Year", willing_to_advise=True,
            completed_courses=[" csc 510 ", "CSC 510", "CSC 540"],
        )

    def test_registration_creates_searchable_profile(self):
        response = self.client.post("/api/auth/register", json=self.payload)
        self.assertEqual(response.status_code, 201, response.get_json())
        body = response.get_json()
        student = body["student"]
        self.assertEqual(student["name"], "Casey Smith")
        self.assertEqual(student["completed_courses"], ["CSC 510", "CSC 540"])
        self.assertFalse(body["confirmation_required"])
        self.assertEqual(self.client.get("/api/auth/me").status_code, 200)
        search = self.client.get("/api/students/search?course=CSC%20510").get_json()["students"]
        self.assertIn(student["id"], [row["id"] for row in search])
        profile = self.client.get(f"/api/students/{student['id']}").get_json()["student"]
        for private_field in ("email", "password", "password_hash", "auth_user_id"):
            self.assertNotIn(private_field, student)
            self.assertNotIn(private_field, profile)

    def test_duplicate_email_is_rejected(self):
        self.assertEqual(self.client.post("/api/auth/register", json=self.payload).status_code, 201)
        duplicate = {**self.payload, "email": "CASEY@EXAMPLE.EDU"}
        response = self.client.post("/api/auth/register", json=duplicate)
        self.assertEqual(response.status_code, 409)

    def test_invalid_registration_payloads_are_rejected(self):
        invalid = [
            None, [], {}, {**self.payload, "name": " "},
            {**self.payload, "name": 123}, {**self.payload, "email": "bad@email"},
            {**self.payload, "password": "short"}, {**self.payload, "password": "x" * 129},
            {**self.payload, "password": None}, {**self.payload, "program": ""},
            {**self.payload, "year": ""}, {**self.payload, "bio": "x" * 2001},
            {**self.payload, "willing_to_advise": "false"},
            {**self.payload, "completed_courses": "CSC 510"},
            {**self.payload, "completed_courses": [123]},
            {**self.payload, "completed_courses": [" "]},
            {**self.payload, "completed_courses": ["CSC 510"] * 51},
        ]
        for payload in invalid:
            with self.subTest(payload=str(payload)[:70]):
                response = self.client.post("/api/auth/register", json=payload)
                self.assertEqual(response.status_code, 400)
        self.assertEqual(self.db.tables["students"], [])
        self.assertEqual(self.db.tables["completed_courses"], [])

    def test_advising_is_opt_in(self):
        payload = {key: value for key, value in self.payload.items() if key != "willing_to_advise"}
        response = self.client.post("/api/auth/register", json=payload)
        self.assertEqual(response.status_code, 201)
        student_id = response.get_json()["student"]["id"]
        search = self.client.get("/api/students/search?course=CSC%20510").get_json()["students"]
        self.assertNotIn(student_id, [row["id"] for row in search])
        search_all = self.client.get("/api/students/search?course=CSC%20510&available=false").get_json()["students"]
        self.assertIn(student_id, [row["id"] for row in search_all])

    def test_confirmation_required_does_not_create_authenticated_session(self):
        self.db.confirmation_required = True
        response = self.client.post("/api/auth/register", json=self.payload)
        self.assertEqual(response.status_code, 201)
        self.assertTrue(response.get_json()["confirmation_required"])
        self.assertEqual(self.client.get("/api/auth/me").status_code, 401)


if __name__ == "__main__":
    unittest.main()
