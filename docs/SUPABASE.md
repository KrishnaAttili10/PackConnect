# Supabase storage

All Flask routes use PostgreSQL hosted by Supabase through Psycopg. Registration,
login accounts, profiles, courses, requests, chat, and notifications share this
database. There is no SQLite runtime or fallback. Flask session authentication
is retained; accounts are not automatically converted to Supabase Auth users.

## Configure and apply migrations

Install `backend/requirements.txt`, then create `backend/.env` using
`backend/.env.example`. Set `SUPABASE_DB_URL` to the project's **Connect → Session
pooler** PostgreSQL connection string, including the database password. This is
separate from the HTTPS `SUPABASE_URL` and from API keys. Percent-encode special
characters in a URL password. SSL is required by default. Keep all credentials
server-side and out of Git.

From the repository root:

```sh
.venv/bin/python backend/migrate.py
.venv/bin/python backend/app.py
```

On Windows use `.\.venv\Scripts\python.exe` in place of `.venv/bin/python`.
The migration runner holds a database advisory lock and applies pending SQL files
and their checksums in one transaction. It tracks them in
`public.packconnect_migrations`; rerunning skips unchanged applied files and
rejects changed ones. Do not mix this runner's history with Supabase CLI history
without reconciling them. A failed migration rolls back the entire run.

The baseline preserves existing tables and rows with `CREATE TABLE IF NOT EXISTS`.
It adds the Flask `accounts` table if missing and enforces case-insensitive email
uniqueness. A follow-up migration permits legacy messages without a Supabase Auth
UUID and backfills request notifications. Existing tables must have compatible
columns and identity/serial ID sequences; the baseline does not repair arbitrary
schema differences. Conflicting unique indexes fail rather than deleting rows.

RLS is enabled and browser-role table grants are revoked. Flask owns authorization
and uses a privileged server database connection. Existing browser clients that
query Supabase tables directly would lose access. The frontend continues to use
Flask `/api` endpoints. No frontend credentials are needed for application storage.

Startup checks account storage and backfills notifications; it does not create
schema or seed fictional students. An old `backend/peer_advice.db` can remain as
an unused backup. It is never opened by the app. Local SQLite data is not
imported automatically; preserve old files before any separate data transfer.
Supabase Auth UUIDs are omitted from public profile responses.

## Verification

Backend tests use isolated schemas on a dedicated local PostgreSQL database,
not your connected project. Set `TEST_DATABASE_URL` to a localhost database with
schema/role creation privileges and `sslmode=disable` for local testing. CI
provides a PostgreSQL 17 service automatically.

```sh
TEST_DATABASE_URL='postgresql://postgres:postgres@127.0.0.1:5432/packconnect_test?sslmode=disable' \
  .venv/bin/python -m unittest discover -s backend -p 'test_*.py' -v
```

The normal suite covers authentication, privacy, transactions and rollback,
foreign keys, permissions, request decisions, chat persistence, notifications,
repeatable migrations, and denied browser-role table privileges.

To explicitly test the connected Supabase project after migration:

```sh
RUN_SUPABASE_INTEGRATION=1 .venv/bin/python -m unittest discover -s backend -p 'test_supabase_integration.py' -v
```

The integration suite exercises the actual Flask routes for registration, login,
profile editing, search, requests, acceptance, private chat, notifications, and
third-party denial, then checks API writes through a separate SQL connection.
It also verifies the optional Supabase SDK with `SUPABASE_URL` and
`SUPABASE_SECRET_KEY` configured. Cleanup removes only the newly inserted IDs in
reverse dependency order. Network failures or process interruption can leave
UUID-tagged `integration-` rows; inspect them before manual removal. Sequence
counters advance even after cleanup.

References: [Supabase PostgreSQL connections](https://supabase.com/docs/guides/database/connecting-to-postgres),
[Psycopg transactions](https://www.psycopg.org/psycopg3/docs/basic/transactions.html).
