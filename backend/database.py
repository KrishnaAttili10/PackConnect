"""Transactional PostgreSQL connections to the configured Supabase database."""

from contextlib import contextmanager

import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict
from psycopg.rows import dict_row


@contextmanager
def connect_database(database_url, schema=None):
    if not database_url:
        raise RuntimeError("Set SUPABASE_DB_URL in backend/.env; SQLite is no longer supported.")
    parameters = conninfo_to_dict(database_url)
    parameters.setdefault("sslmode", "require")
    parameters.setdefault("connect_timeout", "10")
    with psycopg.connect(**parameters, row_factory=dict_row, prepare_threshold=None) as db:
        if schema:
            db.execute(sql.SQL("SET LOCAL search_path TO {}, public").format(sql.Identifier(schema)))
        yield db
