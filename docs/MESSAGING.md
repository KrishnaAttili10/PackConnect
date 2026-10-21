# Advice requests and private conversations

The active storage is SQLite. Restart Flask after pulling this change so
`initialize_database()` adds `advice_requests`, `chat_messages`, and their
indexes. Existing data is retained. No Supabase credentials are required.

## Try it with two accounts

1. Register Alice and Blake with fictional information. Blake must opt into advising.
2. Sign in as Alice in a normal browser window and Blake in a separate browser
   profile or incognito window. Two ordinary tabs share the same session cookie.
3. Alice finds Blake's profile and sends a course, topic, and request message.
4. Alice sees the pending request under **Requests → Outgoing**. Chat is locked.
5. Blake opens **Requests → Incoming** and accepts it.
6. Both accounts now see **Open chat**. Exchange messages; new messages appear
   automatically while the conversation is open.
7. Refresh or sign out/in and confirm that requests and chat history remain.
8. A third account cannot view the request or open its conversation URL.

Fictional seed profiles have no accounts and cannot receive requests. A request
must target another registered, currently available advisor. Identity always
comes from the session, never a client-supplied sender ID or name.

## API

All endpoints below require a signed-in account; missing sessions return 401.

| Method | Path | Behavior |
| --- | --- | --- |
| GET | `/api/requests` | Incoming/outgoing requests belonging to the signed-in user |
| POST | `/api/requests` | Body: `recipient_id`, `course_code` (1–30 chars), `advice_topic` (1–80), `message` (1–1000) |
| PATCH | `/api/requests/<id>` | Body: `status` of `accepted` or `declined`; recipient only |
| GET | `/api/requests/<id>/messages?after_id=0` | Accepted conversation metadata and next 100 messages; `has_more` indicates another batch |
| POST | `/api/requests/<id>/messages` | Body: `body` (1–2000 chars); verified sender ID added by the backend |

An unrelated user receives 404 for private resources. A participant attempting
to chat before acceptance receives 403. Duplicate active requests return 409,
including reverse-direction requests. A declined pair may create a new request.
Repeating the same decision is idempotent; changing a completed decision returns
409. SQL constraints and a conditional update enforce these rules in storage.

Chat history is ordered by message ID and retrieved incrementally. Both request
participants can send messages; no third account can join. Original request text
is displayed as conversation context. The frontend polls chats every three
seconds and refreshes request lists on navigation and every eight seconds.

## Existing messages

Legacy `messages` rows remain untouched. They have no authenticated sender
identity and are not exposed as private chat. The old direct-message route
returns 410, closing the previous path around request acceptance.

## Verification and limits

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s backend -p "test_*.py" -v
cd frontend
npm.cmd run lint
npm.cmd run build
```

The messaging suite covers validation, authentication, identity spoofing,
participants, acceptance/decline, duplicate/reverse requests, persistence,
two-way messages, cursor pagination, retired-route rejection, and preservation
of old messages. Local browser checks exercised three isolated sessions: request
creation, recipient acceptance, two-way polling chat, refresh persistence,
third-user denial, and mobile layout.

In-app bell notifications cover requests, decisions, and new messages. This
implementation has no email/push notifications, read receipts, attachments,
blocking, or message deletion. It uses polling, not WebSockets. Access is private
at the application API level; this does not claim end-to-end encryption. Configure
a persistent private `FLASK_SECRET_KEY` for sessions across backend restarts and
HTTPS with `COOKIE_SECURE=true` for deployment, as described in README.

## Notification API

- `GET /api/notifications`: latest 50 updates plus `unread_count` across all updates.
- `POST /api/notifications/<id>/read`: mark one of your own notifications read.
- `POST /api/notifications/read`: JSON `through_id` marks your notifications up
  to that ID read, so concurrent newer arrivals remain unread.

Authentication is required. Other users' notification IDs return 404. Notification
creation shares the request/decision/message transaction; repeated decisions do
not generate duplicate alerts. Existing pending requests and completed decisions
are backfilled using unique event keys, preserving read state on later startups.
The frontend polls every five seconds, marks clicked alerts read, and supports
outside-click/Escape dismissal. New-message alerts link to the accepted chat;
request-received alerts open Incoming and declined decisions open Outgoing.
