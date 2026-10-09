import tempfile
import unittest
from pathlib import Path

import app as portal


class MessageTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.original_path = portal.DB_PATH
        portal.DB_PATH = Path(self.directory.name) / "test.db"
        portal.initialize_database()
        self.client = portal.app.test_client()

    def tearDown(self):
        portal.DB_PATH = self.original_path
        self.directory.cleanup()

    def test_message_is_trimmed_and_persisted(self):
        response = self.client.post("/api/students/1/messages", json={
            "sender_name": " Casey ", "body": " Any study tips? "
        })
        self.assertEqual(response.status_code, 201)
        message = response.get_json()["message"]
        self.assertEqual(message["sender_name"], "Casey")
        self.assertEqual(message["body"], "Any study tips?")
        self.assertEqual(message["recipient_id"], 1)
        self.assertTrue(message["created_at"])
        with portal.get_db() as db:
            stored = db.execute("SELECT * FROM messages").fetchone()
        self.assertEqual(dict(stored), message)

    def test_invalid_payloads_do_not_save(self):
        for payload in [None, [], {}, {"sender_name": 123, "body": "Hi"},
                        {"sender_name": "Casey", "body": "   "},
                        {"sender_name": "x" * 101, "body": "Hi"},
                        {"sender_name": "Casey", "body": "x" * 2001}]:
            with self.subTest(payload=payload):
                response = self.client.post("/api/students/1/messages", json=payload)
                self.assertEqual(response.status_code, 400)
        with portal.get_db() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM messages").fetchone()[0], 0)

    def test_recipient_must_exist_and_accept_advice(self):
        payload = {"sender_name": "Casey", "body": "Hi"}
        self.assertEqual(self.client.post("/api/students/999/messages", json=payload).status_code, 404)
        with portal.get_db() as db:
            db.execute("UPDATE students SET willing_to_advise = 0 WHERE id = 1")
        self.assertEqual(self.client.post("/api/students/1/messages", json=payload).status_code, 403)


if __name__ == "__main__":
    unittest.main()
