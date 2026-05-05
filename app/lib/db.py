"""Lakebase Postgres connection management.

Uses auto-injected PG* env vars when running on Databricks Apps with a Lakebase
resource binding. Falls back to generating an OAuth token via the SDK for local
development. Always connects to the application database (e.g., `sbar_briefing`)
rather than the default `databricks_postgres`.
"""
import os
import time
import threading
import psycopg2
from psycopg2.extras import Json, RealDictCursor


_lock = threading.Lock()
_token_cache: dict = {"token": None, "expires_at": 0.0}


def _get_password() -> str:
    """Auto-injected PGPASSWORD when bound; otherwise generate via SDK."""
    if pg_password := os.getenv("PGPASSWORD"):
        return pg_password

    now = time.time()
    with _lock:
        if _token_cache["token"] and _token_cache["expires_at"] - now > 120:
            return _token_cache["token"]
        from databricks.sdk import WorkspaceClient
        instance = os.getenv("LAKEBASE_INSTANCE", "hls-lakebase-demo")
        w = WorkspaceClient()
        cred = w.database.generate_database_credential(
            request_id=f"sbar-app-{int(now)}",
            instance_names=[instance],
        )
        _token_cache["token"] = cred.token
        _token_cache["expires_at"] = now + 50 * 60  # ~50 min
        return cred.token


def _get_host() -> str:
    if host := os.getenv("PGHOST"):
        return host
    from databricks.sdk import WorkspaceClient
    instance = os.getenv("LAKEBASE_INSTANCE", "hls-lakebase-demo")
    w = WorkspaceClient()
    return w.database.get_database_instance(name=instance).read_write_dns


def _get_user() -> str:
    if user := os.getenv("PGUSER"):
        return user
    from databricks.sdk import WorkspaceClient
    return WorkspaceClient().current_user.me().user_name


def get_connection():
    """Create a fresh psycopg2 connection per request. Lakebase tokens rotate, so
    we don't pool connections at the app level."""
    return psycopg2.connect(
        host=_get_host(),
        port=int(os.getenv("PGPORT", "5432")),
        user=_get_user(),
        password=_get_password(),
        database=os.getenv("LAKEBASE_PG_DATABASE", "sbar_briefing"),
        sslmode="require",
        connect_timeout=10,
    )


def insert_event(*, user_email: str, user_role: str, session_id: str, sbar_id: str | None,
                 event_type: str, payload: dict) -> str:
    schema = os.getenv("LAKEBASE_PG_SCHEMA", "sbar")
    conn = get_connection()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    f'INSERT INTO "{schema}".audit_events '
                    f"(user_email, user_role, session_id, sbar_id, event_type, payload) "
                    f"VALUES (%s, %s, %s, %s, %s, %s) RETURNING event_id",
                    (user_email, user_role, session_id, sbar_id, event_type, Json(payload)),
                )
                return str(cur.fetchone()[0])
    finally:
        conn.close()


def query(sql: str, params: tuple = ()) -> list[dict]:
    conn = get_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(sql, params)
            return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()
