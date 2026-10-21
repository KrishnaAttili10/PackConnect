import app as portal
from psycopg import IntegrityError
from migrate import MIGRATIONS, migration_sql
from postgres_test_support import PostgresTestCase


class DatabaseInitializationTests(PostgresTestCase):
    def test_initialization_preserves_data_and_does_not_reseed(self):
        portal.initialize_database()
        with portal.get_db() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM students").fetchone()["count"], 4)
            for table in ("accounts", "messages", "current_courses", "advice_requests", "chat_messages", "notifications"):
                with self.subTest(table=table):
                    self.assertEqual(db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()["count"], 0)
            db.execute("DELETE FROM completed_courses")
            db.execute("DELETE FROM students")
        portal.initialize_database()
        with portal.get_db() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM students").fetchone()["count"], 0)

    def test_missing_configuration_does_not_create_local_database(self):
        portal.app.config["SUPABASE_DB_URL"] = None
        with self.assertRaisesRegex(RuntimeError, "SUPABASE_DB_URL"):
            portal.initialize_database()

    def test_failed_transaction_rolls_back_profile_and_courses(self):
        with self.assertRaises(IntegrityError):
            with portal.get_db() as db:
                student_id = db.execute("""
                    INSERT INTO students (name, program, year)
                    VALUES ('Rollback', 'CS', 'First Year') RETURNING id
                """).fetchone()["id"]
                db.execute("INSERT INTO completed_courses (student_id, course_code) VALUES (%s, 'CSC 510')",
                           (student_id,))
                db.execute("INSERT INTO accounts (student_id, email, password_hash) VALUES (-1, 'bad@example.edu', 'hash')")
        with portal.get_db() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM students").fetchone()["count"], 4)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM completed_courses WHERE student_id = %s",
                                        (student_id,)).fetchone()["count"], 0)

    def test_migrations_can_baseline_existing_tables_without_losing_rows(self):
        with portal.get_db() as db:
            for path in sorted(MIGRATIONS.glob("*.sql")):
                db.execute(migration_sql(path).replace("public.", self.schema + "."), prepare=False)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM students").fetchone()["count"], 4)

    def test_browser_roles_have_no_table_privileges(self):
        with portal.get_db() as db:
            for table in ("students", "accounts", "completed_courses", "current_courses",
                          "messages", "advice_requests", "chat_messages", "notifications"):
                for role in ("anon", "authenticated"):
                    for privilege in ("SELECT", "INSERT", "UPDATE", "DELETE"):
                        allowed = db.execute("SELECT has_table_privilege(%s, %s, %s) AS allowed",
                                             (role, f"{self.schema}.{table}", privilege)).fetchone()["allowed"]
                        self.assertFalse(allowed, (table, role, privilege))
