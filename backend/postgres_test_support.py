"""Run each test in a fresh schema on a dedicated local PostgreSQL instance."""

import os
import unittest
from uuid import uuid4

import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict

import app as portal
from migrate import MIGRATIONS, migration_sql
from test_seeds import seed_students


class PostgresTestCase(unittest.TestCase):
    def setUp(self):
        database_url = os.getenv("TEST_DATABASE_URL")
        if not database_url:
            raise RuntimeError("Set TEST_DATABASE_URL to a dedicated local PostgreSQL database.")
        if conninfo_to_dict(database_url).get("host") not in ("127.0.0.1", "localhost", "::1"):
            raise RuntimeError("Tests require a local PostgreSQL host; never use your live Supabase URL.")
        self.schema = "test_" + uuid4().hex
        self.original_url = portal.app.config.get("SUPABASE_DB_URL")
        portal.app.config["SUPABASE_DB_URL"] = database_url
        portal.app.config["TEST_DB_SCHEMA"] = self.schema
        self.addCleanup(self.restore_database)
        with psycopg.connect(database_url, autocommit=True) as db:
            db.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(self.schema)))
            self.addCleanup(self.drop_schema, database_url)
            # Minimal Supabase-owned roles/Auth table for vanilla PostgreSQL CI.
            for role in ("anon", "authenticated", "service_role"):
                if not db.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (role,)).fetchone():
                    db.execute(sql.SQL("CREATE ROLE {} NOLOGIN").format(sql.Identifier(role)))
            db.execute("CREATE SCHEMA IF NOT EXISTS auth")
            db.execute("CREATE TABLE IF NOT EXISTS auth.users (id uuid PRIMARY KEY)")
        with portal.get_db() as db:
            for path in sorted(MIGRATIONS.glob("*.sql")):
                db.execute(migration_sql(path).replace("public.", self.schema + "."), prepare=False)
            seed_students(db)
        portal.initialize_database()

    def restore_database(self):
        portal.app.config["SUPABASE_DB_URL"] = self.original_url
        portal.app.config.pop("TEST_DB_SCHEMA", None)

    def drop_schema(self, database_url):
        with psycopg.connect(database_url, autocommit=True) as db:
            db.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(self.schema)))
