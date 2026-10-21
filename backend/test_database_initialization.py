import tempfile
import unittest
from pathlib import Path

import app as portal


class DatabaseInitializationTests(unittest.TestCase):
    def test_fresh_database_contains_only_fictional_seed_data(self):
        original_path = portal.DB_PATH
        with tempfile.TemporaryDirectory() as directory:
            portal.DB_PATH = Path(directory) / "fresh.db"
            try:
                self.assertFalse(portal.DB_PATH.exists())
                portal.initialize_database()
                with portal.get_db() as db:
                    names = {
                        row["name"] for row in db.execute("SELECT name FROM students")
                    }
                    self.assertEqual(names, {
                        "Alex Morgan", "Jordan Lee", "Taylor Kim", "Sam Patel",
                    })
                    for table in ("accounts", "messages", "current_courses", "advice_requests", "chat_messages"):
                        with self.subTest(table=table):
                            self.assertEqual(
                                db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0],
                                0,
                            )
                client = portal.app.test_client()
                matches = client.get(
                    "/api/students/search?course=CSC%20510"
                ).get_json()["students"]
                self.assertEqual(
                    {student["name"] for student in matches},
                    {"Alex Morgan", "Jordan Lee", "Sam Patel"},
                )
            finally:
                portal.DB_PATH = original_path


if __name__ == "__main__":
    unittest.main()
