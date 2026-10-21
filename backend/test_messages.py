import unittest
from datetime import datetime

import app as portal
from postgres_test_support import PostgresTestCase


class MessagingTests(PostgresTestCase):
    def setUp(self):
        super().setUp()
        self.clients = []
        self.ids = []
        for name in ("Sender", "Recipient", "Outsider"):
            client = portal.app.test_client()
            credentials = {"email": name.lower() + "@example.edu", "password": "a long test password"}
            response = client.post("/api/auth/register", json={
                **credentials, "name": name, "program": "Computer Science", "year": "First Year",
                "willing_to_advise": True, "completed_courses": ["CSC 510"],
            })
            self.ids.append(response.get_json()["student"]["id"])
            self.assertEqual(client.post("/api/auth/login", json=credentials).status_code, 200)
            self.clients.append(client)
        self.sender, self.recipient, self.outsider = self.clients
        self.payload = {"recipient_id": self.ids[1], "course_code": " csc 510 ",
                        "advice_topic": " Projects ", "message": " Any preparation tips? "}

    def create_request(self):
        response = self.sender.post("/api/requests", json=self.payload)
        self.assertEqual(response.status_code, 201, response.get_json())
        return response.get_json()["request"]["id"]

    def accept(self):
        request_id = self.create_request()
        self.assertEqual(self.recipient.patch(f"/api/requests/{request_id}", json={"status": "accepted"}).status_code, 200)
        return request_id

    def test_requests_persist_and_only_participants_list_them(self):
        request_id = self.create_request()
        portal.initialize_database()
        for client in (self.sender, self.recipient):
            rows = client.get("/api/requests").get_json()["requests"]
            self.assertEqual([row["id"] for row in rows], [request_id])
            self.assertEqual(rows[0]["course_code"], "CSC 510")
            self.assertEqual(rows[0]["message"], "Any preparation tips?")
            self.assertNotIn("email", rows[0])
        self.assertEqual(self.outsider.get("/api/requests").get_json()["requests"], [])

    def test_identity_cannot_be_spoofed(self):
        response = self.sender.post("/api/requests", json={**self.payload, "sender_id": self.ids[2], "sender_name": "Impostor"})
        self.assertEqual(response.get_json()["request"]["sender_id"], self.ids[0])
        self.assertEqual(response.get_json()["request"]["sender_name"], "Sender")

    def test_unauthenticated_endpoints(self):
        client = portal.app.test_client()
        for method, path in [("get", "/api/requests"), ("post", "/api/requests"),
                             ("patch", "/api/requests/1"), ("get", "/api/requests/1/messages"),
                             ("post", "/api/requests/1/messages")]:
            with self.subTest(method=method):
                self.assertEqual(getattr(client, method)(path).status_code, 401)

    def test_invalid_request_fields_create_no_records(self):
        invalid = [None, [], {}, *[{**self.payload, key: value} for key, value in [
            ("recipient_id", True), ("recipient_id", "1"), ("recipient_id", 0),
            ("course_code", " "), ("course_code", 123), ("course_code", "x" * 31),
            ("advice_topic", []), ("advice_topic", "x" * 81),
            ("message", " "), ("message", "x" * 1001),
        ]]]
        for payload in invalid:
            with self.subTest(payload=payload):
                self.assertEqual(self.sender.post("/api/requests", json=payload).status_code, 400)
        self.assertEqual(self.sender.get("/api/requests").get_json()["requests"], [])

    def test_self_request_is_rejected(self):
        self.assertEqual(self.sender.post("/api/requests", json={**self.payload, "recipient_id": self.ids[0]}).status_code, 400)

    def test_unknown_and_sample_recipients(self):
        self.assertEqual(self.sender.post("/api/requests", json={**self.payload, "recipient_id": 99999}).status_code, 404)
        self.assertEqual(self.sender.post("/api/requests", json={**self.payload, "recipient_id": 1}).status_code, 400)

    def test_unavailable_recipient(self):
        with portal.get_db() as db:
            db.execute("UPDATE students SET willing_to_advise = false WHERE id = %s", (self.ids[1],))
        self.assertEqual(self.sender.post("/api/requests", json=self.payload).status_code, 400)

    def test_duplicate_and_reverse_pending_requests_are_rejected(self):
        self.create_request()
        self.assertEqual(self.sender.post("/api/requests", json=self.payload).status_code, 409)
        self.assertEqual(self.recipient.post("/api/requests", json={**self.payload, "recipient_id": self.ids[0]}).status_code, 409)

    def test_accepted_pair_cannot_create_another_request(self):
        self.accept()
        self.assertEqual(self.sender.post("/api/requests", json=self.payload).status_code, 409)

    def test_only_recipient_can_respond(self):
        request_id = self.create_request()
        self.assertEqual(self.sender.patch(f"/api/requests/{request_id}", json={"status": "accepted"}).status_code, 403)
        self.assertEqual(self.outsider.patch(f"/api/requests/{request_id}", json={"status": "accepted"}).status_code, 404)
        self.assertEqual(self.recipient.get("/api/requests").get_json()["requests"][0]["status"], "pending")

    def test_invalid_status_and_unknown_request(self):
        request_id = self.create_request()
        for payload in [None, [], {}, {"status": "pending"}, {"status": "other"}, {"status": []}]:
            self.assertEqual(self.recipient.patch(f"/api/requests/{request_id}", json=payload).status_code, 400)
        self.assertEqual(self.recipient.patch("/api/requests/99999", json={"status": "accepted"}).status_code, 404)

    def test_pending_chat_is_locked(self):
        request_id = self.create_request()
        for client in (self.sender, self.recipient):
            self.assertEqual(client.get(f"/api/requests/{request_id}/messages").status_code, 403)
            self.assertEqual(client.post(f"/api/requests/{request_id}/messages", json={"body": "Hello"}).status_code, 403)

    def test_decline_locks_chat_but_allows_a_new_request(self):
        request_id = self.create_request()
        self.assertEqual(self.recipient.patch(f"/api/requests/{request_id}", json={"status": "declined"}).status_code, 200)
        self.assertEqual(self.sender.get(f"/api/requests/{request_id}/messages").status_code, 403)
        self.assertEqual(self.sender.post(f"/api/requests/{request_id}/messages", json={"body": "Hello"}).status_code, 403)
        self.assertNotEqual(request_id, self.create_request())

    def test_response_is_idempotent_but_cannot_be_reversed(self):
        request_id = self.accept()
        self.assertEqual(self.recipient.patch(f"/api/requests/{request_id}", json={"status": "accepted"}).status_code, 200)
        self.assertEqual(self.recipient.patch(f"/api/requests/{request_id}", json={"status": "declined"}).status_code, 409)

    def test_chat_two_way_identity_and_persistence(self):
        request_id = self.accept()
        for client, sender_id, body in [(self.sender, self.ids[0], " Hi there "), (self.recipient, self.ids[1], "Happy to help")]:
            response = client.post(f"/api/requests/{request_id}/messages", json={"body": body, "sender_id": self.ids[2]})
            self.assertEqual(response.status_code, 201)
            self.assertEqual(response.get_json()["message"]["sender_id"], sender_id)
            self.assertIsNotNone(datetime.fromisoformat(response.get_json()["message"]["created_at"]).tzinfo)
        portal.initialize_database()
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
            self.assertEqual(self.sender.post(f"/api/requests/{request_id}/messages", json=payload).status_code, 400)
        self.assertEqual(self.sender.get(f"/api/requests/{request_id}/messages").get_json()["messages"], [])

    def test_message_cursor_pages_without_gaps(self):
        request_id = self.accept()
        with portal.get_db() as db:
            db.cursor().executemany("INSERT INTO chat_messages (request_id, sender_id, body) VALUES (%s, %s, %s)", [(request_id, self.ids[0], str(i)) for i in range(105)])
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
        self.assertEqual(self.sender.post("/api/students/1/messages", json={"body": "Bypass"}).status_code, 410)
        with portal.get_db() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM messages").fetchone()["count"], 0)

    def test_existing_legacy_messages_are_preserved_without_exposure(self):
        with portal.get_db() as db:
            db.execute("INSERT INTO messages (recipient_id, sender_name, body) VALUES (1, 'Legacy', 'Old data')")
        portal.initialize_database()
        with portal.get_db() as db:
            self.assertEqual(db.execute("SELECT body AS count FROM messages").fetchone()["count"], "Old data")
        self.assertEqual(self.sender.get("/api/requests").get_json()["requests"], [])


if __name__ == "__main__":
    unittest.main()
