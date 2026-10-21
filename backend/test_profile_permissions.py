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

    def profile_state(self):
        with portal.get_db() as db:
            return {
                "profile": db.execute("SELECT * FROM students WHERE id = %s",
                                      (self.student_id,)).fetchone(),
                **{table: db.execute(f"SELECT * FROM {table} WHERE student_id = %s ORDER BY id",
                                     (self.student_id,)).fetchall()
                   for table in ("completed_courses", "current_courses")},
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
        for field in ("name", "program", "year", "bio", "interests", "skills", "advice_topics", "willing_to_advise"):
            self.assertEqual(profile[field], self.payload[field])
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

    def test_each_required_profile_field_is_required_without_changing_data(self):
        self.client.post("/api/auth/login", json=self.credentials)
        before = self.profile_state()
        for field in ("name", "program", "year"):
            for value in ("missing", "", "   "):
                with self.subTest(field=field, value=value):
                    payload = {**self.payload, field: value}
                    if value == "missing":
                        payload.pop(field)
                    response = self.client.put(f"/api/students/{self.student_id}", json=payload)
                    self.assertEqual(response.status_code, 400)
                    self.assertIn("error", response.get_json())
                    self.assertEqual(self.profile_state(), before)

    def test_malformed_profile_bodies_return_400_without_changing_data(self):
        self.client.post("/api/auth/login", json=self.credentials)
        before = self.profile_state()
        bodies = [("", "application/json"), ('{"name":', "application/json"),
                  ('{"name":"Owner"}', "text/plain"), ("null", "application/json"),
                  ("[]", "application/json"), ('"text"', "application/json"),
                  ("true", "application/json"), ("42", "application/json")]
        for body, content_type in bodies:
            with self.subTest(body=body, content_type=content_type):
                response = self.client.put(f"/api/students/{self.student_id}",
                                           data=body, content_type=content_type)
                self.assertEqual(response.status_code, 400)
                self.assertIn("error", response.get_json())
                self.assertEqual(self.profile_state(), before)

    def test_invalid_profile_field_types_return_400_without_changing_data(self):
        self.client.post("/api/auth/login", json=self.credentials)
        before = self.profile_state()
        cases = []
        for field in ("name", "program", "year", "bio", "interests", "skills", "advice_topics"):
            cases.extend((field, value) for value in (None, 123, False, [], {}))
        cases.extend(("willing_to_advise", value) for value in (None, "false", 0, [], {}))
        for field in ("completed_courses", "current_courses"):
            cases.extend((field, value) for value in (None, "CSC 510", {}, 42, [None], [123], [{}]))
        for field, value in cases:
            with self.subTest(field=field, value=value):
                response = self.client.put(f"/api/students/{self.student_id}",
                                           json={**self.payload, field: value})
                self.assertEqual(response.status_code, 400)
                self.assertIn("error", response.get_json())
                self.assertEqual(self.profile_state(), before)

    def test_profile_replaces_and_normalizes_completed_and_current_courses(self):
        self.client.post("/api/auth/login", json=self.credentials)
        payload = {**self.payload,
                   "completed_courses": [" csc 540 ", "CSC 540", "CSC 515", " "],
                   "current_courses": [" csc 520 ", "CSC 520", "CSC 522"]}
        for _ in range(2):
            self.assertEqual(self.client.put(f"/api/students/{self.student_id}", json=payload).status_code, 200)
        portal.initialize_database()
        profile = self.client.get(f"/api/students/{self.student_id}").get_json()["student"]
        self.assertEqual(profile["completed_courses"], ["CSC 515", "CSC 540"])
        self.assertEqual(profile["current_courses"], ["CSC 520", "CSC 522"])
        with portal.get_db() as db:
            for table in ("completed_courses", "current_courses"):
                self.assertEqual(db.execute(f"SELECT COUNT(*) FROM {table} WHERE student_id = %s",
                                            (self.student_id,)).fetchone()["count"], 2)

    def test_profile_can_clear_course_lists_and_optional_fields(self):
        self.client.post("/api/auth/login", json=self.credentials)
        self.client.put(f"/api/students/{self.student_id}", json=self.payload)
        payload = {**self.payload, "completed_courses": [], "current_courses": [],
                   "bio": "", "interests": "", "skills": "", "advice_topics": ""}
        response = self.client.put(f"/api/students/{self.student_id}", json=payload)
        self.assertEqual(response.status_code, 200)
        profile = self.client.get(f"/api/students/{self.student_id}").get_json()["student"]
        for field in ("completed_courses", "current_courses", "bio", "interests", "skills", "advice_topics"):
            self.assertEqual(profile[field], payload[field])

    def test_replacing_courses_removes_old_search_match_and_adds_new_one(self):
        self.client.post("/api/auth/login", json=self.credentials)
        initial = {**self.payload, "completed_courses": ["TEST 100"]}
        replacement = {**self.payload, "completed_courses": ["TEST 200"]}
        self.assertEqual(self.client.put(f"/api/students/{self.student_id}", json=initial).status_code, 200)
        self.assertEqual([row["id"] for row in self.client.get("/api/students/search", query_string={"course": "TEST 100"}).get_json()["students"]], [self.student_id])
        self.assertEqual(self.client.put(f"/api/students/{self.student_id}", json=replacement).status_code, 200)
        self.assertEqual(self.client.get("/api/students/search", query_string={"course": "TEST 100"}).get_json()["students"], [])
        self.assertEqual([row["id"] for row in self.client.get("/api/students/search", query_string={"course": "TEST 200"}).get_json()["students"]], [self.student_id])

    def test_advising_toggle_updates_search_visibility(self):
        self.client.post("/api/auth/login", json=self.credentials)
        for willing in (True, False, True):
            with self.subTest(willing=willing):
                payload = {**self.payload, "completed_courses": ["TEST 300"], "willing_to_advise": willing}
                self.assertEqual(self.client.put(f"/api/students/{self.student_id}", json=payload).status_code, 200)
                rows = self.client.get("/api/students/search", query_string={"course": "TEST 300"}).get_json()["students"]
                self.assertEqual([row["id"] for row in rows], [self.student_id] if willing else [])
                rows = self.client.get("/api/students/search", query_string={"course": "TEST 300", "available": "false"}).get_json()["students"]
                self.assertEqual([row["id"] for row in rows], [self.student_id])

    def test_missing_profile_returns_404(self):
        response = self.client.get("/api/students/999999")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.get_json(), {"error": "Student not found"})

    def test_update_deleted_profile_returns_404_without_recreating_records(self):
        self.client.post("/api/auth/login", json=self.credentials)
        with portal.get_db() as db:
            db.execute("DELETE FROM completed_courses WHERE student_id = %s", (self.student_id,))
            db.execute("DELETE FROM accounts WHERE student_id = %s", (self.student_id,))
            db.execute("DELETE FROM students WHERE id = %s", (self.student_id,))
        response = self.client.put(f"/api/students/{self.student_id}", json=self.payload)
        self.assertEqual(response.status_code, 404)
        with portal.get_db() as db:
            for table in ("completed_courses", "current_courses"):
                self.assertEqual(db.execute(f"SELECT COUNT(*) FROM {table} WHERE student_id = %s",
                                            (self.student_id,)).fetchone()["count"], 0)


if __name__ == "__main__":
    unittest.main()
