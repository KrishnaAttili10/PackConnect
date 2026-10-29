# Advisor availability and capacity

Advisors manage settings from **My profile → Edit Profile**:

- **Available to give advice** controls opt-in for new requests.
- **Maximum open advice requests** accepts 1–100; blank means no limit.
  The default is five, including existing profiles after migration.
- **Pause new requests until** resumes requests at the start of that date in
  `America/New_York` time, subject to opt-in and capacity. Clear the date to
  remove a pause immediately. Past dates do not block requests.

Incoming pending and accepted requests consume capacity. Outgoing, declined,
and completed requests do not. Lowering a limit or pausing preserves existing
requests and chats; only new requests are blocked. Declining a request frees its
slot.

Either participant can choose **Complete advice** on an accepted request in
Requests. Completion frees the advisor's slot, preserves message history as
read-only, and allows a new request between the same students. Completion is
final; declined and pending requests cannot be completed. Participant access
controls still apply to messages and request actions.

Search and profiles show availability and occupied slots. The default
availability filter excludes paused, full, and opted-out advisors. Turn it off
to include them. Accepted connections keep their chat links even when the
advisor is now paused or full. Search results refresh when you run a search.

## Database migration

Before running the updated backend against your configured database:

```sh
.venv/bin/python backend/migrate.py
```

On Windows, use `.\.venv\Scripts\python.exe`. Restart the backend afterward.
`20261028000100_advisor_availability.sql` adds settings, an index for active
incoming requests, and the completed status. It retains existing accounts,
profiles, requests, messages, and notification read states. Applying the default
limit does not delete excess requests.

## API behavior

Registration and owner-only profile updates accept `max_open_requests` (integer
1–100 or null) and `pause_until` (YYYY-MM-DD or null). Omitting these fields on
updates preserves stored settings. Invalid values return 400.

Profiles and search summaries include `max_open_requests`, `pause_until`,
`open_request_count`, `availability_status`, and `accepting_requests`. Status is
`available`, `paused`, `at_capacity`, `not_advising`, or `unregistered`.
Availability is computed from settings, identity, the current Eastern date, and
workload; client-supplied availability flags are ignored.

`POST /api/requests` returns 409 for paused or full advisors and creates no
request or notification. The advisor row is locked before counting and
inserting, so concurrent requests cannot overbook the final slot. Profile edits
and lifecycle changes serialize against the same row. Non-key row locks avoid
foreign-key deadlocks for opposite-direction requests.

`PATCH /api/requests/<id>` accepts `completed` from either participant for an
accepted request. Repeating completion is idempotent. Completed conversations
allow GET and return 409 for POST; outsiders still receive 404. Message writes
and completion lock the request row, preventing a late message after completion
commits.

## Verification

Run `npm test`, `npm run lint`, `npm run build`, and the Prettier check from
`frontend/`. Run the backend suite with a dedicated local PostgreSQL database
as described in [Supabase verification](SUPABASE.md#verification).

`backend/test_availability.py` covers settings, validation, ownership, pause
expiry, search filtering, limits, unlimited capacity, preserved connections,
completion and history, concurrent last-slot requests, and opposite-direction
requests. Frontend interaction tests cover saving and clearing settings,
unavailable profiles, existing chats, completion, and read-only history.

Local verification on October 28, 2026 passed 38 frontend tests and 107 backend
methods, with two opt-in live Supabase tests skipped. Lint, formatting, and the
production build passed. Headless Chrome exercised the production build with
isolated PostgreSQL: saving/clearing settings, paused/full search results,
server-side rejection, request/accept/chat/complete, restored capacity, and
read-only history passed at desktop and mobile sizes without JavaScript
exceptions or horizontal overflow. Live Supabase data was not changed.
