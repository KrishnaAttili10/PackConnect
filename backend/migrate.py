"""Apply versioned SQL migrations explicitly: python backend/migrate.py."""

import hashlib
import os
from pathlib import Path

from dotenv import load_dotenv

from database import connect_database


MIGRATIONS = Path(__file__).resolve().parents[1] / "supabase" / "migrations"


def migration_sql(path):
    # The runner owns the transaction, including migration history.
    return "\n".join(line for line in path.read_text().splitlines()
                     if line.strip() not in ("BEGIN;", "COMMIT;"))


def apply_migrations(database_url):
    completed = []
    with connect_database(database_url) as db:
        db.execute("SELECT pg_advisory_xact_lock(728416203)")
        db.execute("""
            CREATE TABLE IF NOT EXISTS public.packconnect_migrations (
                name text PRIMARY KEY,
                sha256 text NOT NULL,
                applied_at timestamptz NOT NULL DEFAULT now()
            )
        """)
        db.execute("ALTER TABLE public.packconnect_migrations ENABLE ROW LEVEL SECURITY")
        db.execute("REVOKE ALL ON public.packconnect_migrations FROM PUBLIC, anon, authenticated")
        applied = {row["name"]: row["sha256"] for row in
                   db.execute("SELECT name, sha256 FROM public.packconnect_migrations")}
        for path in sorted(MIGRATIONS.glob("*.sql")):
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            if path.name in applied:
                if applied[path.name] != digest:
                    raise RuntimeError(f"Applied migration changed: {path.name}")
                continue
            db.execute(migration_sql(path), prepare=False)
            db.execute("INSERT INTO public.packconnect_migrations (name, sha256) VALUES (%s, %s)",
                       (path.name, digest))
            completed.append(path.name)
    for name in completed:
        print(f"Applied {name}")
    if not completed:
        print("Database migrations are up to date.")


if __name__ == "__main__":
    load_dotenv(Path(__file__).parent / ".env")
    try:
        apply_migrations(os.getenv("SUPABASE_DB_URL"))
    except Exception as exc:
        # Connection errors may contain user/host information; never echo a DSN.
        print(f"Migration failed ({type(exc).__name__}). Check configuration and schema compatibility.")
        raise SystemExit(1) from None
