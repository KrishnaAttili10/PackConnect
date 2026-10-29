# Requests, conversations, safety, recovery, and meetings

## Setup

Apply migrations, then restart Flask and refresh the frontend:

```sh
.venv/bin/python backend/migrate.py
```

Use the Python executable for your backend virtual environment. The migration
`20261029000100_community_features.sql` adds expiration dates, terminal request
statuses, blocks, reports, moderator membership, conversation read positions,
meetings, recovery tokens, request limits, and session versions. New tables have
RLS enabled and browser-role access revoked; Flask enforces authorization.
Existing records are preserved. Existing pending requests expire seven days
after their original creation time, including requests already older than that.

## Cancellation and expiration

Senders can cancel pending requests from Outgoing. Cancellation is idempotent,
frees capacity, and notifies the recipient. Accepted advice uses Complete advice
instead. Unanswered requests expire after seven days and notify both students.
Expired requests do not count against capacity, even before status maintenance
runs. Request lists and conversation inboxes maintain expired statuses while the
app is active; sending/deciding requests also checks expiration. History remains
available, and a new request may be sent after cancellation or expiration.

For notification records to be generated while nobody is using the app, schedule:

```sh
.venv/bin/python backend/expire_requests.py
```

Run this periodically using the deployment's scheduler (for example, every five
minutes). No scheduler service is required for capacity enforcement or expiration
when requests are accessed. Notifications are in-app, not expiration emails.

## Conversations

The Conversations page lists accepted and closed conversations, latest message
previews, unread counts, and links, ordered by activity. Read positions are per
participant and advance only through message pages actually fetched. A high
message cursor cannot silently mark unreturned messages read. The inbox refreshes
automatically. Notification bell read state remains a separate per-event setting.

## Blocking, reporting, and moderator review

Student profiles include Block and Report controls. Blocking hides the pair from
signed-in search in both directions, closes active requests/connections, frees
capacity, cancels future meetings, and prevents new requests, messages, and
meeting proposals. Existing message history stays readable by participants.
Blocked students are managed from the Blocked students page. Unblocking permits
new requests but does not reopen closed conversations.

Profiles or individual received messages can be reported with a reason. The
server verifies ownership of message evidence and limits reports to ten per
student per day. Reports are visible only to moderators through Report review;
ordinary students cannot list reports or review them. Moderators resolve or
dismiss reports with a written resolution. Reports do not automatically ban users.

Assign moderator membership deliberately in Supabase SQL, replacing the email:

```sql
INSERT INTO public.staff_members(student_id)
SELECT id FROM public.students
WHERE id IN (
  SELECT student_id FROM public.accounts WHERE lower(email)=lower('moderator@example.edu')
) OR auth_user_id IN (
  SELECT id FROM auth.users WHERE lower(email)=lower('moderator@example.edu')
)
ON CONFLICT DO NOTHING;
```

Sign in again or reload after assigning the role. No account is made a moderator
automatically. A client-supplied profile flag cannot grant moderator access.

## Password recovery

Forgot password opens the recovery form. Configure these server environment
variables using `backend/.env.example`:

- `PUBLIC_APP_URL`: the frontend origin/base URL, without a fragment or query.
  Use HTTPS in production; localhost HTTP is supported for development.
- `SMTP_HOST`, `SMTP_PORT`, and `SMTP_FROM`: the email sender connection.
- `SMTP_USERNAME` and `SMTP_PASSWORD`: credentials when required by the sender.
- `SMTP_SSL=true` for implicit TLS (usually port 465). Otherwise STARTTLS is used
  (usually port 587). Certificate verification is enabled.
- Linked Supabase Auth accounts also require `SUPABASE_URL` and the server-only
  `SUPABASE_SECRET_KEY` to update their provider password. Local accounts do not.

Without sender configuration, the UI explicitly reports that recovery email is
not configured. No tokens are returned by the API or printed in logs. Existing
and unknown email addresses get the same generic successful response when the
sender is configured. Delivery errors invalidate the token and are logged without
private details. SMTP must be connected before real emails can be delivered.

Links expire after 30 minutes, use random single-use tokens stored only as SHA-256
hashes, and cannot be reused. Requesting a newer link invalidates earlier links.
The endpoint limits requests to five per IP/hour and three links per account/hour;
confirmations are limited to twenty attempts per IP/hour. Password reset requires
12–128 characters, invalidates outstanding links and existing app sessions, and
keeps Supabase and Flask account types separate. Users sign in again afterward.
When deploying behind a proxy, configure the trusted client-IP handling in the
hosting layer; this implementation does not trust arbitrary forwarded headers.

## Meetings

Participants propose a future meeting in an accepted, unblocked conversation.
Times are entered in the device's displayed time zone and sent with explicit UTC
offsets. Meetings last 15–120 minutes and can be proposed up to 180 days ahead.
The other participant accepts or declines; a proposer cannot self-accept.
Accepted meetings cannot overlap another accepted meeting for either student.
Ordered participant locks serialize concurrent acceptances. Proposed meetings
can be cancelled, and either participant can cancel an accepted meeting.
Completing or blocking a connection cancels its future meetings.

Accepted meetings provide a participant-only iCalendar download for import into
calendar apps. It includes UTC times and escaped/folded text fields. It does not
write to Google Calendar or send calendar invitations automatically.

## Verification

Run the frontend tests, lint, build, and formatting check as described in README.
Run backend tests with a dedicated localhost PostgreSQL database. SMTP delivery
and Supabase Auth password updates are mocked in automated recovery tests; no
real recovery email is sent by tests.

On October 29, 2026, 52 frontend tests and 126 backend tests passed, with two live
Supabase integration tests skipped. Desktop/mobile Chrome checked cancellation,
expiration, inbox previews/unread counts, meeting proposal/acceptance/calendar
export, message reporting/moderation, block/unblock, and a full password reset
through a captured test email. There were no JavaScript exceptions or horizontal
overflow in that check. Lint, formatting, and the production build passed.
