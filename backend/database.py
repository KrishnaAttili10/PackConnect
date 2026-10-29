"""Pooled PostgreSQL connections with transaction-local schema isolation."""

from contextlib import contextmanager
import atexit
from threading import Lock

from psycopg import sql
from psycopg.conninfo import conninfo_to_dict
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool


_pools = {}
_pool_lock = Lock()


def close_pools():
    with _pool_lock:
        for pool in _pools.values():
            pool.close()
        _pools.clear()


atexit.register(close_pools)


def connection_pool(database_url):
    # Open lazily, after worker startup. Each process has at most four connections
    # per configured database; test schemas share a pool but never a transaction.
    with _pool_lock:
        if database_url not in _pools:
            parameters = conninfo_to_dict(database_url)
            parameters.setdefault("sslmode", "require")
            parameters.setdefault("connect_timeout", "10")
            pool = ConnectionPool(
                kwargs={**parameters, "row_factory": dict_row, "prepare_threshold": None},
                min_size=0, max_size=4, open=False, timeout=10,
                max_idle=60, reconnect_timeout=10,
            )
            pool.open()
            _pools[database_url] = pool
        return _pools[database_url]


@contextmanager
def connect_database(database_url, schema=None):
    if not database_url:
        raise RuntimeError("Set SUPABASE_DB_URL in backend/.env; SQLite is no longer supported.")
    with connection_pool(database_url).connection() as db:
        if schema:
            db.execute(sql.SQL("SET LOCAL search_path TO {}, public").format(sql.Identifier(schema)))
        yield db
