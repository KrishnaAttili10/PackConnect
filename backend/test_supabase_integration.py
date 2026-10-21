"""Explicit live test: RUN_SUPABASE_INTEGRATION=1 python -m unittest ...

Uses the same server-side client as Flask. Normal CI never contacts Supabase.
Only newly inserted, UUID-tagged records are removed during cleanup.
"""

import os
import unittest
from datetime import datetime, timezone
from uuid import uuid4

import app as portal


@unittest.skipUnless(
    os.getenv("RUN_SUPABASE_INTEGRATION") == "1",
    "Set RUN_SUPABASE_INTEGRATION=1 to test the connected project",
)
class SupabaseIntegrationTests(unittest.TestCase):
    def test_flask_routes_use_supabase_postgres(self):
        marker = f"integration-{uuid4()}"
        clients = []
        ids = []

        def remove_student(student_id):
            with portal.get_db() as db:
                for table in ("accounts", "completed_courses", "current_courses"):
                    db.execute(f"DELETE FROM {table} WHERE student_id = %s", (student_id,))
                db.execute("DELETE FROM students WHERE id = %s", (student_id,))

        for suffix in ("sender", "recipient", "outsider"):
            client = portal.app.test_client()
            credentials = {"email": f"{marker}-{suffix}@example.invalid",
                           "password": "integration test password"}
            response = client.post("/api/auth/register", json={
                **credentials, "name": marker + suffix, "program": marker,
                "year": "Test", "willing_to_advise": True,
                "completed_courses": ["TEST 000"],
            })
            self.assertEqual(response.status_code, 201, response.get_json())
            student_id = response.get_json()["student"]["id"]
            self.addCleanup(remove_student, student_id)
            ids.append(student_id)
            self.assertEqual(client.post("/api/auth/login", json=credentials).status_code, 200)
            clients.append(client)
        sender, recipient, outsider = clients
        matches = sender.get(f"/api/students/search?program={marker}").get_json()["students"]
        self.assertEqual({row["id"] for row in matches}, set(ids))
        update = recipient.put(f"/api/students/{ids[1]}", json={
            "name": marker + "-updated", "program": marker, "year": "Test",
            "willing_to_advise": True, "completed_courses": ["TEST 000"],
            "current_courses": ["TEST 001"],
        })
        self.assertEqual(update.status_code, 200)
        self.assertEqual(recipient.get("/api/auth/me").get_json()["student"]["current_courses"], ["TEST 001"])
        response = sender.post("/api/requests", json={
            "recipient_id": ids[1], "course_code": "TEST 000",
            "advice_topic": "Integration", "message": marker,
        })
        self.assertEqual(response.status_code, 201, response.get_json())
        request_id = response.get_json()["request"]["id"]

        def remove_request():
            with portal.get_db() as db:
                for table in ("notifications", "chat_messages"):
                    db.execute(f"DELETE FROM {table} WHERE request_id = %s", (request_id,))
                db.execute("DELETE FROM advice_requests WHERE id = %s", (request_id,))

        self.addCleanup(remove_request)
        self.assertEqual(outsider.get(f"/api/requests/{request_id}/messages").status_code, 404)
        self.assertEqual(sender.get(f"/api/requests/{request_id}/messages").status_code, 403)
        self.assertEqual(recipient.patch(f"/api/requests/{request_id}", json={"status": "accepted"}).status_code, 200)
        self.assertEqual(sender.post(f"/api/requests/{request_id}/messages", json={"body": marker}).status_code, 201)
        self.assertEqual(recipient.get(f"/api/requests/{request_id}/messages").get_json()["messages"][0]["body"], marker)
        feed = recipient.get("/api/notifications").get_json()
        self.assertEqual(feed["unread_count"], 2)
        self.assertEqual(recipient.post("/api/notifications/read", json={
            "through_id": feed["notifications"][0]["id"],
        }).status_code, 200)
        self.assertEqual(recipient.get("/api/notifications").get_json()["unread_count"], 0)
        # A separate SQL connection verifies that API writes reached PostgreSQL.
        with portal.get_db() as db:
            self.assertEqual(db.execute("SELECT body FROM chat_messages WHERE request_id = %s",
                                        (request_id,)).fetchone()["body"], marker)

    def test_profile_request_chat_and_notification_round_trip(self):
        self.assertIsNotNone(portal.supabase, "Configure backend/.env first")
        client = portal.supabase
        marker = f"integration-{uuid4()}"
        # Register cleanup immediately after each successful insert, in reverse
        # dependency order, so failures in assertions also remove test records.
        def insert(table, payload):
            rows = client.table(table).insert(payload).execute().data
            self.assertTrue(rows, f"No inserted row returned from {table}")
            row = rows[0]
            self.addCleanup(
                lambda: client.table(table).delete().eq("id", row["id"]).execute()
            )
            return row

        sender = insert("students", {
            "name": marker + "-sender", "program": "Integration test",
            "year": "Test", "willing_to_advise": False,
        })
        recipient = insert("students", {
            "name": marker + "-recipient", "program": "Integration test",
            "year": "Test", "willing_to_advise": True,
        })
        for table in ("completed_courses", "current_courses"):
            course = insert(table, {
                "student_id": recipient["id"], "course_code": "TEST 000",
            })
            stored = client.table(table).select("student_id,course_code").eq(
                "id", course["id"]
            ).single().execute().data
            self.assertEqual(stored["student_id"], recipient["id"])
            self.assertEqual(stored["course_code"], "TEST 000")

        advice_request = insert("advice_requests", {
            "sender_id": sender["id"], "recipient_id": recipient["id"],
            "course_code": "TEST 000", "advice_topic": "Integration test",
            "message": marker,
        })
        self.assertEqual(advice_request["status"], "pending")
        client.table("advice_requests").update({"status": "accepted"}).eq(
            "id", advice_request["id"]
        ).execute()
        stored_request = client.table("advice_requests").select("status").eq(
            "id", advice_request["id"]
        ).single().execute().data
        self.assertEqual(stored_request["status"], "accepted")

        message = insert("chat_messages", {
            "request_id": advice_request["id"],
            "sender_id": sender["id"], "body": marker,
        })
        stored_message = client.table("chat_messages").select("body,sender_id").eq(
            "id", message["id"]
        ).single().execute().data
        self.assertEqual(stored_message, {"body": marker, "sender_id": sender["id"]})
        notification = insert("notifications", {
            "user_id": recipient["id"], "actor_id": sender["id"],
            "request_id": advice_request["id"], "kind": "message",
            "event_key": marker,
        })
        self.assertIsNone(notification["read_at"])
        client.table("notifications").update({
            "read_at": datetime.now(timezone.utc).isoformat(),
        }).eq("id", notification["id"]).execute()
        stored_notification = client.table("notifications").select("read_at").eq(
            "id", notification["id"]
        ).single().execute().data
        self.assertIsNotNone(stored_notification["read_at"])


if __name__ == "__main__":
    unittest.main()
