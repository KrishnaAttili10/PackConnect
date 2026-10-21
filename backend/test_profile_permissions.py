
import unittest
import app as portal
from testing_supabase import FakeSupabase, build_test_app, signed_in_client


class ProfilePermissionsTests(unittest.TestCase):
    def setUp(self):
        self.db = FakeSupabase()
        self.app = build_test_app(portal, self.db)
        self.owner_id, self.owner_auth_id = self.db.seed_user("Owner", "owner@example.edu")
        self.other_id, self.other_auth_id = self.db.seed_user("Other", "other@example.edu")
        self.owner = signed_in_client(self.app, self.owner_id, self.owner_auth_id)
        self.other = signed_in_client(self.app, self.other_id, self.other_auth_id)
        self.anon = self.app.test_client()
        self.payload = {
            "name": "Updated Owner", "program": "Computer Science", "year": "Second Year",
            "bio": "New bio", "interests": "Databases", "skills": "Python",
            "advice_topics": "Projects", "willing_to_advise": True,
            "completed_courses": ["csc 510", "CSC 540"], "current_courses": ["CSC 515"],
        }

    def test_unauthenticated_update_is_rejected(self):
        response = self.anon.put(f"/api/students/{self.owner_id}", json=self.payload)
        self.assertEqual(response.status_code, 401)

    def test_other_user_cannot_modify_profile_or_courses(self):
        before = self.other.get(f"/api/students/{self.owner_id}").get_json()
        response = self.other.put(f"/api/students/{self.owner_id}", json=self.payload)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(before, self.other.get(f"/api/students/{self.owner_id}").get_json())

    def test_owner_update_persists_and_updates_current_user(self):
        response = self.owner.put(f"/api/students/{self.owner_id}", json=self.payload)
        self.assertEqual(response.status_code, 200, response.get_json())
        profile = self.owner.get("/api/auth/me").get_json()["student"]
        self.assertEqual(profile["name"], "Updated Owner")
        self.assertEqual(profile["completed_courses"], ["CSC 510", "CSC 540"])
        self.assertEqual(profile["current_courses"], ["CSC 515"])
        matches = self.owner.get("/api/students/search?course=CSC%20540&skills=Python").get_json()["students"]
        self.assertEqual([row["id"] for row in matches], [self.owner_id])

    def test_invalid_payloads_are_rejected_without_changes(self):
        before = self.owner.get(f"/api/students/{self.owner_id}").get_json()
        for payload in [None, [], {}, {**self.payload, "name": " "}]:
            with self.subTest(payload=str(payload)[:60]):
                self.assertEqual(self.owner.put(f"/api/students/{self.owner_id}", json=payload).status_code, 400)
        self.assertEqual(before, self.owner.get(f"/api/students/{self.owner_id}").get_json())

    def test_unknown_profile_returns_404(self):
        self.assertEqual(self.owner.get("/api/students/99999").status_code, 404)


if __name__ == "__main__":
    unittest.main()
