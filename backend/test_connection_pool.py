"""Connection reuse must preserve transaction and schema boundaries."""

import app as portal
from database import connect_database
from postgres_test_support import PostgresTestCase


class ConnectionPoolTests(PostgresTestCase):
    def test_sequential_transactions_reuse_physical_connections(self):
        pids = []
        for _ in range(12):
            with portal.get_db() as db:
                pids.append(db.execute("SELECT pg_backend_pid() AS pid").fetchone()["pid"])
        self.assertLessEqual(len(set(pids)), 4)

    def test_exception_rolls_back_and_connection_remains_usable(self):
        with self.assertRaisesRegex(ValueError, "rollback fixture"):
            with portal.get_db() as db:
                db.execute("INSERT INTO students (name, program, year) VALUES ('pool-rollback', 'CS', '1')")
                raise ValueError("rollback fixture")
        with portal.get_db() as db:
            self.assertEqual(db.execute("SELECT count(*) AS n FROM students WHERE name = 'pool-rollback'").fetchone()["n"], 0)

    def test_schema_search_path_does_not_leak_after_returning_connection(self):
        for _ in range(8):
            with portal.get_db() as db:
                self.assertEqual(db.execute("SELECT current_schema() AS name").fetchone()["name"], self.schema)
            with connect_database(portal.app.config["SUPABASE_DB_URL"]) as db:
                self.assertEqual(db.execute("SELECT current_schema() AS name").fetchone()["name"], 'public')
