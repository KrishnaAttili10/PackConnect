import unittest

import app as portal
from postgres_test_support import PostgresTestCase


class ProfilePermissionsTests(PostgresTestCase):
    def setUp(self):
        super().setUp()
        self.client = portal.app.test_client()
        self.credentials = {"email": "owner@example.edu", "password": "a long test password"}
        response = self.client.post("/api/auth/register", json={
            **self.credentials, "name": "Owner", "program": "Computer Science",
            "year": "First Year", "completed_courses": ["CSC 510"],
        })
        self.student_id = response.get_json()["student"]["id"]
        self.payload = {
            "name": "Updated Owner", "program": "Computer Science", "year": "Second Year",
            "bio": "New bio", "interests": "Databases", "skills": "Python",
            "advice_topics": "Projects", "willing_to_advise": True,
            "completed_courses": ["csc 510", "CSC 540"], "current_courses": ["CSC 515"],
        }

    def test_unauthenticated_update_is_rejected_without_changes(self):
        before = self.client.get(f"/api/students/{self.student_id}").get_json()
        response = self.client.put(f"/api/students/{self.student_id}", json=self.payload)
        self.assertEqual(response.status_code, 401)
        self.assertEqual(before, self.client.get(f"/api/students/{self.student_id}").get_json())

    def test_standalone_profile_creation_is_retired(self):
        response = self.client.post("/api/students", json=self.payload)
        self.assertEqual(response.status_code, 410)
        with portal.get_db() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM students").fetchone()["count"], 5)

    def test_other_user_cannot_modify_profile_or_courses(self):
        self.client.post("/api/auth/login", json=self.credentials)
        before = self.client.get("/api/students/1").get_json()
        self.assertEqual(self.client.put("/api/students/1", json=self.payload).status_code, 403)
        self.assertEqual(before, self.client.get("/api/students/1").get_json())

    def test_owner_update_persists_and_updates_current_user(self):
        self.client.post("/api/auth/login", json=self.credentials)
        response = self.client.put(f"/api/students/{self.student_id}", json=self.payload)
        self.assertEqual(response.status_code, 200)
        profile = self.client.get("/api/auth/me").get_json()["student"]
        self.assertEqual(profile["name"], "Updated Owner")
        self.assertEqual(profile["completed_courses"], ["CSC 510", "CSC 540"])
        self.assertEqual(profile["current_courses"], ["CSC 515"])
        matches = self.client.get("/api/students/search?course=CSC%20540&skills=Python").get_json()["students"]
        self.assertEqual([row["id"] for row in matches], [self.student_id])

    def test_invalid_payload_is_rejected_without_changes(self):
        self.client.post("/api/auth/login", json=self.credentials)
        before = self.client.get(f"/api/students/{self.student_id}").get_json()
        for payload in [None, [], {}, {**self.payload, "name": " "}]:
            with self.subTest(payload=payload):
                self.assertEqual(self.client.put(f"/api/students/{self.student_id}", json=payload).status_code, 400)
        self.assertEqual(before, self.client.get(f"/api/students/{self.student_id}").get_json())


if __name__ == "__main__":
    unittest.main()
