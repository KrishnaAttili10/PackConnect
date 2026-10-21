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
