"""Advisor availability, settings, lifecycle, and concurrent capacity enforcement."""

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier

import app as portal
from postgres_test_support import PostgresTestCase


class AdvisorAvailabilityTests(PostgresTestCase):
    def setUp(self):
        super().setUp()
        self.ids = []
        self.clients = []
        with portal.get_db() as db:
            self.today = db.execute("SELECT (CURRENT_TIMESTAMP AT TIME ZONE 'America/New_York')::date AS today").fetchone()["today"]
            for name in ("Advisor", "First", "Second", "Third"):
                student_id = db.execute("""INSERT INTO students (name, program, year, willing_to_advise)
                    VALUES (%s, 'CS', '1', true) RETURNING id""", (name,)).fetchone()["id"]
                db.execute("INSERT INTO accounts (student_id, email, password_hash) VALUES (%s, %s, 'unused')",
                           (student_id, name + '@example.test'))
                db.execute("INSERT INTO completed_courses (student_id, course_code) VALUES (%s, 'CSC 510')", (student_id,))
                self.ids.append(student_id)
        for student_id in self.ids:
            client = portal.app.test_client()
            with client.session_transaction() as session:
                session["student_id"] = student_id
            self.clients.append(client)
        self.advisor = self.clients[0]
        self.profile_payload = {"name": "Advisor", "program": "CS", "year": "1",
                                "willing_to_advise": True, "completed_courses": ["CSC 510"]}

    def edit(self, **fields):
        return self.advisor.put(f'/api/students/{self.ids[0]}', json={**self.profile_payload, **fields})

    def profile(self):
        return self.advisor.get(f'/api/students/{self.ids[0]}').get_json()["student"]

    def send(self, sender=1, recipient=None):
        return self.clients[sender].post('/api/requests', json={
            "recipient_id": recipient or self.ids[0], "course_code": "CSC 510",
            "advice_topic": "Projects", "message": "Can you help?",
        })

    def search_ids(self, **filters):
        return [row["id"] for row in self.advisor.get('/api/students/search',
                query_string={"course": "CSC 510", **filters}).get_json()["students"]]

    def test_settings_persist_and_omitted_fields_are_preserved(self):
        until = (self.today + timedelta(days=2)).isoformat()
        response = self.edit(max_open_requests=2, pause_until=until)
        self.assertEqual(response.status_code, 200)
        profile = response.get_json()["student"]
        self.assertEqual((profile["max_open_requests"], profile["pause_until"]), (2, until))
        self.assertEqual(profile["availability_status"], "paused")
        self.edit(bio="Updated without changing settings")
        self.assertEqual((self.profile()["max_open_requests"], self.profile()["pause_until"]), (2, until))
        self.edit(max_open_requests=None, pause_until=None)
        self.assertIsNone(self.profile()["max_open_requests"])
        self.assertIsNone(self.profile()["pause_until"])
        self.assertTrue(self.profile()["accepting_requests"])

    def test_invalid_settings_rejected_without_profile_changes(self):
        before = self.profile()
        for field, values in {
            "max_open_requests": [0, -1, 101, True, 1.5, "2", [], {}],
            "pause_until": [True, 123, [], {}, "", "2026-02-30", "20261028", "2026-1-2", "2026-10-28T12:00:00Z"],
        }.items():
            for value in values:
                with self.subTest(field=field, value=value):
                    self.assertEqual(self.edit(**{field: value}).status_code, 400)
                    self.assertEqual(self.profile(), before)

    def test_pause_filters_search_and_rejects_requests_without_notifications(self):
        self.edit(pause_until=(self.today + timedelta(days=1)).isoformat())
        self.assertNotIn(self.ids[0], self.search_ids())
        self.assertIn(self.ids[0], self.search_ids(available="false"))
        response = self.send()
        self.assertEqual(response.status_code, 409)
        self.assertIn('paused', response.get_json()["error"])
        with portal.get_db() as db:
            self.assertEqual(db.execute("SELECT count(*) AS n FROM advice_requests").fetchone()["n"], 0)
            self.assertEqual(db.execute("SELECT count(*) AS n FROM notifications").fetchone()["n"], 0)

    def test_pause_resumes_on_selected_date_and_keeps_opt_out_in_force(self):
        for day in (self.today, self.today - timedelta(days=1)):
            self.edit(pause_until=day.isoformat())
            self.assertTrue(self.profile()["accepting_requests"])
            self.assertIn(self.ids[0], self.search_ids())
        self.edit(willing_to_advise=False)
        self.assertFalse(self.profile()["accepting_requests"])
        self.assertEqual(self.send().status_code, 400)

    def test_pending_and_accepted_consume_capacity_decline_and_completion_release_it(self):
        self.edit(max_open_requests=1)
        request_id = self.send().get_json()["request"]["id"]
        self.assertEqual(self.profile()["open_request_count"], 1)
        self.assertEqual(self.profile()["availability_status"], "at_capacity")
        self.assertNotIn(self.ids[0], self.search_ids())
        self.assertEqual(self.send(sender=2).status_code, 409)
        self.assertEqual(self.advisor.patch(f'/api/requests/{request_id}', json={"status": "declined"}).status_code, 200)
        self.assertTrue(self.profile()["accepting_requests"])
        request_id = self.send(sender=2).get_json()["request"]["id"]
        self.advisor.patch(f'/api/requests/{request_id}', json={"status": "accepted"})
        self.assertEqual(self.send(sender=3).status_code, 409)
        self.clients[2].post(f'/api/requests/{request_id}/messages', json={"body": "Thank you"})
        self.assertEqual(self.advisor.patch(f'/api/requests/{request_id}', json={"status": "completed"}).status_code, 200)
        self.assertTrue(self.profile()["accepting_requests"])
        history = self.clients[2].get(f'/api/requests/{request_id}/messages')
        self.assertEqual(history.status_code, 200)
        self.assertEqual(history.get_json()["messages"][0]["body"], "Thank you")
        self.assertEqual(self.clients[2].post(f'/api/requests/{request_id}/messages', json={"body": "Closed"}).status_code, 409)
        self.assertEqual(self.send(sender=2).status_code, 201)

    def test_completion_requires_a_participant_and_an_accepted_request(self):
        request_id = self.send().get_json()["request"]["id"]
        url = f'/api/requests/{request_id}'
        self.assertEqual(self.advisor.patch(url, json={"status": "completed"}).status_code, 409)
        self.advisor.patch(url, json={"status": "accepted"})
        self.assertEqual(self.clients[2].patch(url, json={"status": "completed"}).status_code, 404)
        self.assertEqual(self.clients[1].patch(url, json={"status": "completed"}).status_code, 200)
        self.assertEqual(self.advisor.patch(url, json={"status": "completed"}).status_code, 200)
        self.assertEqual(self.advisor.patch(url, json={"status": "accepted"}).status_code, 409)

    def test_pausing_or_lowering_limit_preserves_existing_connections(self):
        request_id = self.send().get_json()["request"]["id"]
        self.send(sender=2)
        self.edit(max_open_requests=1, pause_until=(self.today + timedelta(days=1)).isoformat())
        self.assertEqual(self.advisor.patch(f'/api/requests/{request_id}', json={"status": "accepted"}).status_code, 200)
        self.assertEqual(self.clients[1].post(f'/api/requests/{request_id}/messages', json={"body": "Still connected"}).status_code, 201)
        self.assertEqual(self.profile()["open_request_count"], 2)

    def test_outgoing_requests_do_not_consume_advisor_capacity(self):
        self.edit(max_open_requests=1)
        self.send(sender=0, recipient=self.ids[1])
        self.assertEqual(self.profile()["open_request_count"], 0)
        self.assertEqual(self.send(sender=2).status_code, 201)

    def test_unlimited_setting_allows_requests_above_previous_limit(self):
        self.edit(max_open_requests=1)
        self.assertEqual(self.send().status_code, 201)
        self.assertEqual(self.send(sender=2).status_code, 409)
        self.edit(max_open_requests=None)
        self.assertEqual(self.send(sender=2).status_code, 201)
        self.assertEqual(self.send(sender=3).status_code, 201)
        self.assertTrue(self.profile()["accepting_requests"])
        self.assertEqual(self.profile()["open_request_count"], 3)

    def test_settings_require_owner_and_accepting_state_cannot_be_spoofed(self):
        url = f'/api/students/{self.ids[0]}'
        payload = {**self.profile_payload, "max_open_requests": 1}
        self.assertEqual(portal.app.test_client().put(url, json=payload).status_code, 401)
        self.assertEqual(self.clients[1].put(url, json=payload).status_code, 403)
        self.assertEqual(self.profile()["max_open_requests"], 5)
        self.edit(pause_until=(self.today + timedelta(days=1)).isoformat(), accepting_requests=True)
        self.assertFalse(self.profile()["accepting_requests"])
        self.assertEqual(self.send().status_code, 409)

    def test_registration_validates_and_persists_initial_availability(self):
        payload = {"name": "New Advisor", "program": "CS", "year": "1",
                   "email": "new@example.test", "password": "a long test password", "willing_to_advise": True}
        client = portal.app.test_client()
        for fields in ({"max_open_requests": False}, {"max_open_requests": 101}, {"pause_until": "2026-02-30"}):
            self.assertEqual(client.post('/api/auth/register', json={**payload, **fields}).status_code, 400)
        until = (self.today + timedelta(days=1)).isoformat()
        response = client.post('/api/auth/register', json={**payload, "max_open_requests": 2, "pause_until": until})
        self.assertEqual(response.status_code, 201, response.get_json())
        student = response.get_json()["student"]
        self.assertEqual((student["max_open_requests"], student["pause_until"]), (2, until))
        profile = client.get(f'/api/students/{student["id"]}').get_json()["student"]
        self.assertEqual(profile["availability_status"], "paused")

    def test_concurrent_senders_cannot_overbook_last_slot(self):
        self.edit(max_open_requests=1)
        barrier = Barrier(2)
        def send(sender):
            barrier.wait(timeout=5)
            return self.send(sender).status_code
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(send, (1, 2)))
        self.assertEqual(sorted(results), [201, 409])
        self.assertEqual(self.profile()["open_request_count"], 1)

    def test_opposite_direction_requests_do_not_deadlock_or_duplicate(self):
        barrier = Barrier(2)
        def send(sender):
            barrier.wait(timeout=5)
            return self.send(sender=sender, recipient=self.ids[1 - sender]).status_code
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(send, (0, 1)))
        self.assertEqual(sorted(results), [201, 409])
