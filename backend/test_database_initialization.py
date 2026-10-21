
import unittest
import app as portal
from testing_supabase import FakeSupabase, build_test_app


class SupabaseConfigurationTests(unittest.TestCase):
    def setUp(self):
        self.db = FakeSupabase()
        self.app = build_test_app(portal, self.db)
        self.client = self.app.test_client()

    def test_health_reports_supabase(self):
        response = self.client.get("/api/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {"status": "ok", "database": "supabase"})

    def test_empty_student_search_is_successful(self):
        response = self.client.get("/api/students/search")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {"students": []})

    def test_protected_routes_require_authentication(self):
        for method, path in (
            ("get", "/api/auth/me"), ("get", "/api/requests"),
            ("post", "/api/requests"), ("get", "/api/notifications"),
        ):
            with self.subTest(method=method, path=path):
                response = getattr(self.client, method)(path, json={} if method == "post" else None)
                self.assertEqual(response.status_code, 401)

    def test_backend_source_has_no_sqlite_database_operations(self):
        from pathlib import Path
        source_dir = Path(portal.__file__).parent
        for filename in ("app.py", "messaging.py"):
            text = (source_dir / filename).read_text().lower()
            self.assertNotIn("import sqlite3", text)
            self.assertNotIn("sqlite3.connect", text)
            self.assertNotIn("initialize_database(", text)


if __name__ == "__main__":
    unittest.main()
