
import unittest
import app as portal
from testing_supabase import FakeSupabase, build_test_app, signed_in_client


class NotificationTests(unittest.TestCase):
    def setUp(self):
        self.db = FakeSupabase()
        self.app = build_test_app(portal, self.db)
        self.ids = []
        self.auth_ids = []
        for name, email in (
            ("Sender", "sender@example.edu"),
            ("Recipient", "recipient@example.edu"),
            ("Outsider", "outsider@example.edu"),
        ):
            sid, uid = self.db.seed_user(name, email)
            self.ids.append(sid)
            self.auth_ids.append(uid)
        self.sender = signed_in_client(self.app, self.ids[0], self.auth_ids[0])
        self.recipient = signed_in_client(self.app, self.ids[1], self.auth_ids[1])
        self.outsider = signed_in_client(self.app, self.ids[2], self.auth_ids[2])
        self.anon = self.app.test_client()

    def create_request(self):
        response = self.sender.post("/api/requests", json={
            "recipient_id": self.ids[1], "course_code": "CSC 510",
            "advice_topic": "Projects", "message": "Private context",
        })
        self.assertEqual(response.status_code, 201, response.get_json())
        return response.get_json()["request"]["id"]

    def feed(self, client):
        response = client.get("/api/notifications")
        self.assertEqual(response.status_code, 200, response.get_json())
        return response.get_json()

    def test_empty_feed(self):
        self.assertEqual(self.feed(self.sender), {"notifications": [], "unread_count": 0})

    def test_request_notifies_only_recipient_without_private_body(self):
        request_id = self.create_request()
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
        request_id = self.create_request()
        for _ in range(2):
            self.recipient.patch(f"/api/requests/{request_id}", json={"status": "accepted"})
        feed = self.feed(self.sender)
        self.assertEqual(feed["unread_count"], 1)
        self.assertEqual(feed["notifications"][0]["kind"], "accepted")

    def test_decline_notifies_sender(self):
        request_id = self.create_request()
        self.recipient.patch(f"/api/requests/{request_id}", json={"status": "declined"})
        self.assertEqual(self.feed(self.sender)["notifications"][0]["kind"], "declined")

    def test_message_notifies_peer_without_body_preview(self):
        request_id = self.create_request()
        self.recipient.patch(f"/api/requests/{request_id}", json={"status": "accepted"})
        self.sender.post(f"/api/requests/{request_id}/messages", json={"body": "Private message"})
        item = self.feed(self.recipient)["notifications"][0]
        self.assertEqual(item["kind"], "message")
        self.assertEqual(item["actor_name"], "Sender")
        self.assertNotIn("body", item)
        self.recipient.post(f"/api/requests/{request_id}/messages", json={"body": "Reply"})
        self.assertEqual(self.feed(self.sender)["notifications"][0]["kind"], "message")

    def test_read_is_owned_idempotent_and_persistent(self):
        self.create_request()
        item_id = self.feed(self.recipient)["notifications"][0]["id"]
        for _ in range(2):
            self.assertEqual(self.recipient.post(f"/api/notifications/{item_id}/read").status_code, 200)
        feed = self.feed(self.recipient)
        self.assertEqual(feed["unread_count"], 0)
        self.assertEqual(len(feed["notifications"]), 1)
        self.assertIsNotNone(feed["notifications"][0]["read_at"])

    def test_other_users_cannot_mark_notification_read(self):
        self.create_request()
        item_id = self.feed(self.recipient)["notifications"][0]["id"]
        for client in (self.sender, self.outsider):
            self.assertEqual(client.post(f"/api/notifications/{item_id}/read").status_code, 404)
        self.assertEqual(self.feed(self.recipient)["unread_count"], 1)
        self.assertEqual(self.recipient.post("/api/notifications/999999/read").status_code, 404)

    def test_mark_all_respects_cutoff_and_user(self):
        request_id = self.create_request()
        cutoff = self.feed(self.recipient)["notifications"][0]["id"]
        self.recipient.patch(f"/api/requests/{request_id}", json={"status": "accepted"})
        self.sender.post(f"/api/requests/{request_id}/messages", json={"body": "New event"})
        self.recipient.post("/api/notifications/read", json={"through_id": cutoff})
        self.assertEqual(self.feed(self.recipient)["unread_count"], 1)
        self.assertEqual(self.feed(self.sender)["unread_count"], 1)

    def test_bulk_read_validates_cutoff(self):
        for payload in [None, [], {}, {"through_id": True}, {"through_id": -1},
                        {"through_id": "1"}, {"through_id": 2**64}]:
            with self.subTest(payload=str(payload)[:50]):
                self.assertEqual(self.sender.post("/api/notifications/read", json=payload).status_code, 400)

    def test_feed_is_bounded_but_count_includes_older_unread(self):
        request_id = self.create_request()
        self.db.table("notifications").insert([
            {"user_id": self.ids[1], "actor_id": self.ids[0], "request_id": request_id,
             "kind": "message", "event_key": f"fixture:{i}"}
            for i in range(55)
        ]).execute()
        feed = self.feed(self.recipient)
        self.assertEqual(len(feed["notifications"]), 50)
        self.assertEqual(feed["unread_count"], 56)
        self.assertEqual([n["id"] for n in feed["notifications"]], sorted(
            [n["id"] for n in feed["notifications"]], reverse=True))
        self.recipient.post("/api/notifications/read", json={"through_id": feed["notifications"][0]["id"]})
        self.assertEqual(self.feed(self.recipient)["unread_count"], 0)

    def test_authentication_required(self):
        self.assertEqual(self.anon.get("/api/notifications").status_code, 401)
        self.assertEqual(self.anon.post("/api/notifications/1/read").status_code, 401)
        self.assertEqual(self.anon.post("/api/notifications/read", json={"through_id": 1}).status_code, 401)


if __name__ == "__main__":
    unittest.main()
