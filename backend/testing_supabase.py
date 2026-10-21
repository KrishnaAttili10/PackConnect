
"""In-memory Supabase/PostgREST/Auth test doubles. No network or real database access."""
from copy import deepcopy
from datetime import datetime, timezone
from types import SimpleNamespace
import re
import uuid


def now():
    return datetime.now(timezone.utc).isoformat()


class FakeResponse:
    def __init__(self, data):
        self.data = data


class FakeQuery:
    def __init__(self, client, table):
        self.client = client
        self.table_name = table
        self.operation = "select"
        self.columns = "*"
        self.payload = None
        self.filters = []
        self.sorts = []
        self.row_limit = None

    def select(self, columns="*", **kwargs):
        self.operation, self.columns = "select", columns
        return self

    def insert(self, payload):
        self.operation, self.payload = "insert", payload
        return self

    def update(self, payload):
        self.operation, self.payload = "update", payload
        return self

    def delete(self):
        self.operation = "delete"
        return self

    def eq(self, field, value):
        self.filters.append(("eq", field, value))
        return self

    def in_(self, field, values):
        self.filters.append(("in", field, list(values)))
        return self

    def ilike(self, field, pattern):
        self.filters.append(("ilike", field, pattern))
        return self

    def gt(self, field, value):
        self.filters.append(("gt", field, value))
        return self

    def lte(self, field, value):
        self.filters.append(("lte", field, value))
        return self

    def is_(self, field, value):
        self.filters.append(("is", field, value))
        return self

    def order(self, field, desc=False):
        self.sorts.append((field, desc))
        return self

    def limit(self, amount):
        self.row_limit = amount
        return self

    def _matches(self, row):
        for op, field, value in self.filters:
            actual = row.get(field)
            if op == "eq" and actual != value:
                return False
            if op == "in" and actual not in value:
                return False
            if op == "ilike":
                needle = str(value).strip("%").casefold()
                if needle not in str(actual or "").casefold():
                    return False
            if op == "gt":
                try:
                    if not actual > value:
                        return False
                except TypeError:
                    return False
            if op == "lte":
                try:
                    if not actual <= value:
                        return False
                except TypeError:
                    return False
            if op == "is" and value == "null" and actual is not None:
                return False
            if op == "is" and value != "null" and actual is not value:
                return False
        return True

    def _defaults(self, row):
        table = self.table_name
        row.setdefault("id", self.client.next_id(table))
        if table == "students":
            row.setdefault("auth_user_id", None)
            row.setdefault("name", "")
            row.setdefault("program", "")
            row.setdefault("year", "")
            row.setdefault("bio", "")
            row.setdefault("interests", "")
            row.setdefault("skills", "")
            row.setdefault("advice_topics", "")
            row.setdefault("willing_to_advise", False)
            row.setdefault("created_at", now())
        elif table in ("completed_courses", "current_courses"):
            pass
        elif table == "advice_requests":
            row.setdefault("status", "pending")
            row.setdefault("created_at", now())
        elif table == "chat_messages":
            row.setdefault("created_at", now())
        elif table == "notifications":
            row.setdefault("read_at", None)
            row.setdefault("created_at", now())
        return row

    def _check_constraints(self, row):
        rows = self.client.tables[self.table_name]
        if self.table_name == "students" and row.get("auth_user_id"):
            if any(r.get("auth_user_id") == row["auth_user_id"] for r in rows):
                raise Exception("duplicate key violates unique constraint students_auth_user_id_key")
        if self.table_name == "completed_courses":
            if any(r.get("student_id") == row.get("student_id") and r.get("course_code") == row.get("course_code") for r in rows):
                raise Exception("duplicate key violates unique constraint completed_courses_student_id_course_code_key")
        if self.table_name == "advice_requests" and row.get("status", "pending") in ("pending", "accepted"):
            a, b = row.get("sender_id"), row.get("recipient_id")
            for r in rows:
                if r.get("status") in ("pending", "accepted") and {r.get("sender_id"), r.get("recipient_id")} == {a, b}:
                    raise Exception("duplicate key violates unique constraint active_advice_pair")
        if self.table_name == "notifications":
            if any(r.get("event_key") == row.get("event_key") for r in rows):
                raise Exception("duplicate key violates unique constraint notifications_event_key_key")

    def execute(self):
        rows = self.client.tables.setdefault(self.table_name, [])
        if self.operation == "insert":
            payloads = self.payload if isinstance(self.payload, list) else [self.payload]
            inserted = []
            for payload in payloads:
                row = self._defaults(deepcopy(payload))
                self._check_constraints(row)
                rows.append(row)
                inserted.append(deepcopy(row))
            return FakeResponse(inserted)
        matched = [row for row in rows if self._matches(row)]
        if self.operation == "delete":
            deleted_ids = {id(row) for row in matched}
            self.client.tables[self.table_name] = [row for row in rows if id(row) not in deleted_ids]
            return FakeResponse(deepcopy(matched))
        if self.operation == "update":
            for row in matched:
                row.update(deepcopy(self.payload))
            return FakeResponse(deepcopy(matched))
        result = list(matched)
        for field, desc in reversed(self.sorts):
            result.sort(key=lambda row: (row.get(field) is None, row.get(field)), reverse=desc)
        if self.row_limit is not None:
            result = result[:self.row_limit]
        if self.columns.strip() != "*":
            columns = [part.strip() for part in self.columns.split(",")]
            result = [{key: row.get(key) for key in columns} for row in result]
        return FakeResponse(deepcopy(result))


class FakeAuth:
    def __init__(self, client):
        self.client = client
        self.auth = self
        self.admin = self

    def _public_user(self, record, identities=None):
        return SimpleNamespace(
            id=record["id"],
            email=record["email"],
            identities=identities if identities is not None else [{"identity_id": record["id"]}],
        )

    def sign_up(self, payload):
        email = payload["email"].strip().lower()
        password = payload["password"]
        existing = self.client.users_by_email.get(email)
        if existing:
            return SimpleNamespace(user=self._public_user(existing, identities=[]), session=None)
        record = {"id": str(uuid.uuid4()), "email": email, "password": password}
        self.client.users_by_email[email] = record
        self.client.users_by_id[record["id"]] = record
        session = None if self.client.confirmation_required else SimpleNamespace(access_token="fake-token")
        return SimpleNamespace(user=self._public_user(record), session=session)

    def sign_in_with_password(self, payload):
        email = payload["email"].strip().lower()
        record = self.client.users_by_email.get(email)
        if not record or record["password"] != payload["password"]:
            raise Exception("Invalid login credentials")
        return SimpleNamespace(user=self._public_user(record), session=SimpleNamespace(access_token="fake-token"))

    def delete_user(self, user_id):
        record = self.client.users_by_id.pop(str(user_id), None)
        if record:
            self.client.users_by_email.pop(record["email"], None)
        return SimpleNamespace(user=None)


class FakeSupabase:
    TABLES = ("students", "completed_courses", "current_courses", "advice_requests", "chat_messages", "notifications")

    def __init__(self, confirmation_required=False):
        self.tables = {name: [] for name in self.TABLES}
        self.users_by_email = {}
        self.users_by_id = {}
        self.confirmation_required = confirmation_required
        self.auth = FakeAuth(self)

    def table(self, name):
        if name not in self.tables:
            self.tables[name] = []
        return FakeQuery(self, name)

    def next_id(self, table):
        return max([row.get("id", 0) for row in self.tables.setdefault(table, [])] + [0]) + 1

    def seed_user(self, name, email, password="a long test password", program="Computer Science", year="First Year", willing_to_advise=True):
        record = {"id": str(uuid.uuid4()), "email": email.lower(), "password": password}
        self.users_by_email[record["email"]] = record
        self.users_by_id[record["id"]] = record
        inserted = self.table("students").insert({
            "auth_user_id": record["id"], "name": name, "program": program, "year": year,
            "willing_to_advise": willing_to_advise,
        }).execute().data[0]
        return inserted["id"], record["id"]


def build_test_app(portal, fake):
    """Use real route functions but bind messaging routes to an isolated fake database."""
    from flask import Flask
    from types import SimpleNamespace
    portal.supabase = fake
    portal.auth_supabase = SimpleNamespace(auth=fake.auth)
    test_app = Flask("packconnect-test-app")
    test_app.config.update(SECRET_KEY="test-only-session-secret", TESTING=True)
    for rule in portal.app.url_map.iter_rules():
        if rule.endpoint == "static" or rule.endpoint.startswith("messaging."):
            continue
        methods = sorted(rule.methods - {"HEAD", "OPTIONS"})
        test_app.add_url_rule(
            rule.rule, endpoint=rule.endpoint,
            view_func=portal.app.view_functions[rule.endpoint], methods=methods,
        )
    from messaging import create_messaging_blueprint
    test_app.register_blueprint(create_messaging_blueprint(fake))
    return test_app


def signed_in_client(app, student_id, auth_user_id):
    client = app.test_client()
    with client.session_transaction() as session:
        session["student_id"] = student_id
        session["auth_user_id"] = auth_user_id
    return client
