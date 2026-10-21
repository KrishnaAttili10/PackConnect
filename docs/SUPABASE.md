# Supabase schema and connection verification

Flask initializes a server-only Supabase client from `backend/.env`. Application
routes still use SQLite. This step adds a PostgreSQL schema baseline and a live
test; it does not switch route storage, migrate existing data, or change login.

## Schema baseline

`supabase/migrations/20261021000100_packconnect_schema.sql` creates profiles,
Flask accounts, completed/current courses, legacy messages, advice requests,
chat messages, and notifications. IDs accept explicit values for a later SQLite
import. After importing explicit IDs, reset identity sequences above imported
maximum IDs before accepting new writes.

The baseline retains the existing project's optional `students.auth_user_id`
and legacy `messages.sender_user_id` fields. Supabase Auth and Flask accounts
remain separate; no accounts or password hashes are converted automatically.
PostgreSQL stores availability as a boolean and timestamps with time zones.

On an existing project, `CREATE TABLE IF NOT EXISTS` preserves existing tables
and data; it does not reconcile differing column definitions or constraints.
Review existing schema before applying. Unique-index creation deliberately fails
and rolls back if existing rows violate uniqueness; it never deletes conflicts.
All tables must have an identity/serial `id` sequence.

RLS is enabled, browser-role grants are revoked, and the server `service_role`
gets data access. Existing browser-based Supabase clients would lose table access.
Flask must continue checking sessions, ownership, and conversation membership:
the server secret bypasses RLS. Never put it in frontend environment variables.

## Apply

API keys permit data operations, not arbitrary schema migrations. To apply with
the Supabase CLI, authenticate, initialize CLI configuration if needed, link the
intended project, inspect pending migrations, then push:

```sh
supabase init
supabase login
supabase link --project-ref YOUR_PROJECT_REF
supabase db push --dry-run
supabase db push
```

For a project already managed with migrations, reconcile the remote migration
history first. Alternatively, run the migration SQL in the project's SQL Editor;
record that manual application before using CLI migrations later. Do not use
`db reset` against the connected project.

## Verify read/write access

From the repository root, with backend dependencies installed:

```sh
RUN_SUPABASE_INTEGRATION=1 .venv/bin/python -m unittest discover -s backend -p 'test_supabase_integration.py' -v
```

The test uses Flask's configured Supabase client to create two temporary profiles,
write/read course records, create and accept an advice request, persist a chat
message, and mark a notification read. Cleanup deletes only those inserted IDs
in reverse dependency order, including after assertion failures. An interrupted
process or a network failure during cleanup can leave records whose names start
with `integration-`; inspect them before removing them manually. Identity
sequences advance even when temporary records are deleted.

This test covers the existing connected tables. It does not test legacy messages,
Flask accounts, browser-role permissions, or Flask API authorization. It can pass
before the baseline is applied, so success is not proof of migration completion.
Normal test discovery skips this test unless explicitly enabled.

References: [Supabase migrations](https://supabase.com/docs/guides/deployment/database-migrations),
[row-level security](https://supabase.com/docs/guides/database/postgres/row-level-security).
