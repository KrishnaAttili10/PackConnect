import tempfile
import unittest
from pathlib import Path

import app as portal


class NotificationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.password_hash = portal.generate_password_hash("a long test password")

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.original_path = portal.DB_PATH
        portal.DB_PATH = Path(self.directory.name) / "notifications.db"
        portal.initialize_database()
        self.ids = []
        self.clients = []
        with portal.get_db() as db:
            for name in ("Sender", "Recipient", "Outsider"):
                student_id = db.execute("INSERT INTO students (name, program, year, willing_to_advise) VALUES (?, 'CS', 'First Year', 1)", (name,)).lastrowid
                db.execute("INSERT INTO accounts (student_id, email, password_hash) VALUES (?, ?, ?)",
                           (student_id, name.lower() + "@example.edu", self.password_hash))
                self.ids.append(student_id)
                client = portal.app.test_client()
                with client.session_transaction() as session:
                    session["student_id"] = student_id
                self.clients.append(client)
        self.sender, self.recipient, self.outsider = self.clients

    def tearDown(self):
        portal.DB_PATH = self.original_path
        self.directory.cleanup()

    def request(self):
        response = self.sender.post("/api/requests", json={"recipient_id": self.ids[1], "course_code": "CSC 510", "advice_topic": "Projects", "message": "Private context"})
        self.assertEqual(response.status_code, 201)
        return response.get_json()["request"]["id"]

    def feed(self, client):
        return client.get("/api/notifications").get_json()

    def test_empty_feed(self):
        self.assertEqual(self.feed(self.sender), {"notifications": [], "unread_count": 0})

    def test_request_notifies_only_recipient_without_private_body(self):
        request_id = self.request()
        feed = self.feed(self.recipient)
        self.assertEqual(feed["unread_count"], 1)
        item = feed["notifications"][0]
        self.assertEqual(item["request_id"], request_id)
        self.assertEqual(item["kind"], "request_received")
        self.assertEqual(item["actor_name"], "Sender")
        self.assertNotIn("message", item)
        self.assertEqual(self.feed(self.sender)["unread_count"], 0)
        self.assertEqual(self.feed(self.outsider)["notifications"], [])

    def test_acceptance_notifies_sender_once(self):
        request_id = self.request()
        for _ in range(2):
            self.recipient.patch(f"/api/requests/{request_id}", json={"status": "accepted"})
        feed = self.feed(self.sender)
        self.assertEqual(feed["unread_count"], 1)
        self.assertEqual(feed["notifications"][0]["kind"], "accepted")

    def test_decline_notifies_sender(self):
        request_id = self.request()
        self.recipient.patch(f"/api/requests/{request_id}", json={"status": "declined"})
        self.assertEqual(self.feed(self.sender)["notifications"][0]["kind"], "declined")

    def test_message_notifies_peer_without_body_preview(self):
        request_id = self.request()
        self.recipient.patch(f"/api/requests/{request_id}", json={"status": "accepted"})
        self.sender.post(f"/api/requests/{request_id}/messages", json={"body": "Private message"})
        item = self.feed(self.recipient)["notifications"][0]
        self.assertEqual(item["kind"], "message")
        self.assertEqual(item["actor_name"], "Sender")
        self.assertNotIn("body", item)
        self.recipient.post(f"/api/requests/{request_id}/messages", json={"body": "Reply"})
        self.assertEqual(self.feed(self.sender)["notifications"][0]["kind"], "message")

    def test_read_is_owned_idempotent_and_persistent(self):
        self.request()
        item_id = self.feed(self.recipient)["notifications"][0]["id"]
        for _ in range(2):
            self.assertEqual(self.recipient.post(f"/api/notifications/{item_id}/read").status_code, 200)
        portal.initialize_database()
        feed = self.feed(self.recipient)
        self.assertEqual(feed["unread_count"], 0)
        self.assertEqual(len(feed["notifications"]), 1)
        self.assertIsNotNone(feed["notifications"][0]["read_at"])

    def test_other_users_cannot_mark_notification_read(self):
        self.request()
        item_id = self.feed(self.recipient)["notifications"][0]["id"]
        for client in (self.sender, self.outsider):
            self.assertEqual(client.post(f"/api/notifications/{item_id}/read").status_code, 404)
        self.assertEqual(self.feed(self.recipient)["unread_count"], 1)
        self.assertEqual(self.recipient.post("/api/notifications/999999/read").status_code, 404)

    def test_authentication_required(self):
        client = portal.app.test_client()
        self.assertEqual(client.get("/api/notifications").status_code, 401)
        self.assertEqual(client.post("/api/notifications/1/read").status_code, 401)
        self.assertEqual(client.post("/api/notifications/read", json={"through_id": 1}).status_code, 401)

    def test_mark_all_does_not_read_newer_events_or_other_users(self):
        request_id = self.request()
        cutoff = self.feed(self.recipient)["notifications"][0]["id"]
        self.recipient.patch(f"/api/requests/{request_id}", json={"status": "accepted"})
        self.sender.post(f"/api/requests/{request_id}/messages", json={"body": "New event"})
        self.recipient.post("/api/notifications/read", json={"through_id": cutoff})
        self.assertEqual(self.feed(self.recipient)["unread_count"], 1)
        self.assertEqual(self.feed(self.sender)["unread_count"], 1)

    def test_bulk_read_validates_cutoff(self):
        for payload in [None, [], {}, {"through_id": True}, {"through_id": -1}, {"through_id": "1"}, {"through_id": 2**64}]:
            with self.subTest(payload=payload):
                self.assertEqual(self.sender.post("/api/notifications/read", json=payload).status_code, 400)

    def test_feed_is_bounded_but_count_includes_older_unread(self):
        request_id = self.request()
        with portal.get_db() as db:
            db.executemany("INSERT INTO notifications (user_id, actor_id, request_id, kind, event_key) VALUES (?, ?, ?, 'message', ?)",
                           [(self.ids[1], self.ids[0], request_id, f"fixture:{i}") for i in range(55)])
        feed = self.feed(self.recipient)
        self.assertEqual(len(feed["notifications"]), 50)
        self.assertEqual(feed["unread_count"], 56)
        self.assertEqual([n["id"] for n in feed["notifications"]], sorted([n["id"] for n in feed["notifications"]], reverse=True))
        self.recipient.post("/api/notifications/read", json={"through_id": feed["notifications"][0]["id"]})
        self.assertEqual(self.feed(self.recipient)["unread_count"], 0)

    def test_backfill_for_existing_requests_is_repeatable(self):
        request_id = self.request()
        self.recipient.patch(f"/api/requests/{request_id}", json={"status": "accepted"})
        with portal.get_db() as db:
            db.execute("DELETE FROM notifications")
        portal.initialize_database()
        portal.initialize_database()
        self.assertEqual(len(self.feed(self.sender)["notifications"]), 1)
        self.assertEqual(self.feed(self.sender)["notifications"][0]["kind"], "accepted")

    def test_rejected_actions_do_not_emit_updates(self):
        request_id = self.request()
        self.sender.patch(f"/api/requests/{request_id}", json={"status": "accepted"})
        self.sender.post(f"/api/requests/{request_id}/messages", json={"body": "Locked"})
        self.assertEqual(self.feed(self.sender)["unread_count"], 0)
        self.assertEqual(self.feed(self.recipient)["unread_count"], 1)


if __name__ == "__main__":
    unittest.main()
