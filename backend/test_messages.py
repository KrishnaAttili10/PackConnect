
import unittest
import app as portal
from testing_supabase import FakeSupabase, build_test_app, signed_in_client


class MessagingTests(unittest.TestCase):
    def setUp(self):
        self.db = FakeSupabase()
        self.app = build_test_app(portal, self.db)
        self.ids = []
        self.auth_ids = []
        for name, email, willing in (
            ("Sender", "sender@example.edu", True),
            ("Recipient", "recipient@example.edu", True),
            ("Outsider", "outsider@example.edu", True),
            ("Unavailable", "unavailable@example.edu", False),
        ):
            sid, uid = self.db.seed_user(name, email, willing_to_advise=willing)
            self.ids.append(sid)
            self.auth_ids.append(uid)
        self.sender = signed_in_client(self.app, self.ids[0], self.auth_ids[0])
        self.recipient = signed_in_client(self.app, self.ids[1], self.auth_ids[1])
        self.outsider = signed_in_client(self.app, self.ids[2], self.auth_ids[2])
        self.unavailable = signed_in_client(self.app, self.ids[3], self.auth_ids[3])
        self.anon = self.app.test_client()

    def payload(self, recipient_id=None):
        return {
            "recipient_id": self.ids[1] if recipient_id is None else recipient_id,
            "course_code": "csc 510", "advice_topic": "Projects",
            "message": "Could I ask about the course project?",
        }

    def create_request(self, client=None, recipient_id=None):
        client = client or self.sender
        response = client.post("/api/requests", json=self.payload(recipient_id))
        self.assertEqual(response.status_code, 201, response.get_json())
        return response.get_json()["request"]["id"]

    def accept(self):
        request_id = self.create_request()
        response = self.recipient.patch(f"/api/requests/{request_id}", json={"status": "accepted"})
        self.assertEqual(response.status_code, 200, response.get_json())
        return request_id

    def test_requests_persist_and_only_participants_list_them(self):
        request_id = self.create_request()
        self.assertEqual([r["id"] for r in self.sender.get("/api/requests").get_json()["requests"]], [request_id])
        self.assertEqual([r["id"] for r in self.recipient.get("/api/requests").get_json()["requests"]], [request_id])
        self.assertEqual(self.outsider.get("/api/requests").get_json()["requests"], [])

    def test_duplicate_and_reverse_pending_requests_are_rejected(self):
        self.create_request()
        self.assertEqual(self.sender.post("/api/requests", json=self.payload()).status_code, 409)
        self.assertEqual(self.recipient.post("/api/requests", json=self.payload(self.ids[0])).status_code, 409)

    def test_accepted_pair_cannot_create_another_request(self):
        self.accept()
        self.assertEqual(self.sender.post("/api/requests", json=self.payload()).status_code, 409)

    def test_decline_locks_chat_but_allows_a_new_request(self):
        request_id = self.create_request()
        self.assertEqual(self.recipient.patch(f"/api/requests/{request_id}", json={"status": "declined"}).status_code, 200)
        self.assertEqual(self.sender.get(f"/api/requests/{request_id}/messages").status_code, 403)
        self.assertEqual(self.sender.post("/api/requests", json=self.payload()).status_code, 201)

    def test_self_request_is_rejected(self):
        self.assertEqual(self.sender.post("/api/requests", json=self.payload(self.ids[0])).status_code, 400)

    def test_unavailable_recipient(self):
        response = self.sender.post("/api/requests", json=self.payload(self.ids[3]))
        self.assertEqual(response.status_code, 400)

    def test_invalid_request_fields_create_no_records(self):
        before = len(self.db.tables["advice_requests"])
        for payload in [None, [], {}, {**self.payload(), "recipient_id": True},
                        {**self.payload(), "course_code": " "},
                        {**self.payload(), "advice_topic": " "},
                        {**self.payload(), "message": "x" * 1001}]:
            with self.subTest(payload=str(payload)[:60]):
                self.assertEqual(self.sender.post("/api/requests", json=payload).status_code, 400)
        self.assertEqual(len(self.db.tables["advice_requests"]), before)

    def test_only_recipient_can_respond_and_status_cannot_be_reversed(self):
        request_id = self.create_request()
        self.assertEqual(self.sender.patch(f"/api/requests/{request_id}", json={"status": "accepted"}).status_code, 403)
        self.assertEqual(self.outsider.patch(f"/api/requests/{request_id}", json={"status": "accepted"}).status_code, 404)
        self.assertEqual(self.recipient.patch(f"/api/requests/{request_id}", json={"status": "accepted"}).status_code, 200)
        self.assertEqual(self.recipient.patch(f"/api/requests/{request_id}", json={"status": "declined"}).status_code, 409)
        self.assertEqual(self.recipient.patch(f"/api/requests/{request_id}", json={"status": "accepted"}).status_code, 200)

    def test_invalid_status_and_unknown_request(self):
        self.assertEqual(self.recipient.patch("/api/requests/99999", json={"status": "accepted"}).status_code, 404)
        request_id = self.create_request()
        self.assertEqual(self.recipient.patch(f"/api/requests/{request_id}", json={"status": "pending"}).status_code, 400)

    def test_pending_chat_is_locked(self):
        request_id = self.create_request()
        self.assertEqual(self.sender.get(f"/api/requests/{request_id}/messages").status_code, 403)
        self.assertEqual(self.sender.post(f"/api/requests/{request_id}/messages", json={"body": "Hello"}).status_code, 403)

    def test_chat_identity_and_persistence(self):
        request_id = self.accept()
        first = self.sender.post(f"/api/requests/{request_id}/messages", json={"body": "Hi there", "sender_id": self.ids[2]})
        self.assertEqual(first.status_code, 201, first.get_json())
        self.assertEqual(first.get_json()["message"]["sender_id"], self.ids[0])
        self.assertEqual(self.recipient.post(f"/api/requests/{request_id}/messages", json={"body": "Happy to help"}).status_code, 201)
        messages = self.sender.get(f"/api/requests/{request_id}/messages").get_json()["messages"]
        self.assertEqual([row["body"] for row in messages], ["Hi there", "Happy to help"])
        self.assertEqual(self.recipient.get(f"/api/requests/{request_id}/messages").get_json()["messages"], messages)

    def test_outsider_cannot_read_or_send_chat(self):
        request_id = self.accept()
        self.assertEqual(self.outsider.get(f"/api/requests/{request_id}/messages").status_code, 404)
        self.assertEqual(self.outsider.post(f"/api/requests/{request_id}/messages", json={"body": "Intrude"}).status_code, 404)
        self.assertEqual(self.sender.get("/api/requests/99999/messages").status_code, 404)

    def test_invalid_message_bodies_are_not_saved(self):
        request_id = self.accept()
        for payload in [None, [], {}, {"body": []}, {"body": " "}, {"body": "x" * 2001}]:
            with self.subTest(payload=str(payload)[:40]):
                self.assertEqual(self.sender.post(f"/api/requests/{request_id}/messages", json=payload).status_code, 400)
        self.assertEqual(self.sender.get(f"/api/requests/{request_id}/messages").get_json()["messages"], [])

    def test_message_cursor_pages_without_gaps(self):
        request_id = self.accept()
        self.db.table("chat_messages").insert([
            {"request_id": request_id, "sender_id": self.ids[0], "body": str(i)}
            for i in range(105)
        ]).execute()
        first = self.sender.get(f"/api/requests/{request_id}/messages").get_json()
        self.assertEqual(len(first["messages"]), 100)
        self.assertTrue(first["has_more"])
        cursor = first["messages"][-1]["id"]
        second = self.sender.get(f"/api/requests/{request_id}/messages?after_id={cursor}").get_json()
        self.assertEqual(len(second["messages"]), 5)
        self.assertFalse(second["has_more"])
        self.assertGreater(second["messages"][0]["id"], cursor)
        for cursor in ["-1", "abc", "9" * 30]:
            self.assertEqual(self.sender.get(f"/api/requests/{request_id}/messages?after_id={cursor}").status_code, 400)

    def test_old_direct_message_route_cannot_bypass_acceptance(self):
        self.assertEqual(self.sender.post(f"/api/students/{self.ids[1]}/messages", json={"body": "Bypass"}).status_code, 410)
        self.assertEqual(self.db.tables["chat_messages"], [])

    def test_unauthenticated_endpoints(self):
        self.assertEqual(self.anon.get("/api/requests").status_code, 401)
        self.assertEqual(self.anon.post("/api/requests", json=self.payload()).status_code, 401)


if __name__ == "__main__":
    unittest.main()
