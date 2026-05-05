"""Draft CRUD against Lakebase.

Each draft is a row in `sbar.drafts`. Source documents uploaded for the draft
live in `/Volumes/<catalog>/<schema>/draft_inputs/<draft_id>/...` so the LLM
agent can read them by path during generation.
"""
import os
import json
import uuid
import logging
from datetime import datetime, timezone
from psycopg2.extras import Json

from .db import get_connection, query

log = logging.getLogger(__name__)

DRAFT_INPUTS_VOLUME_PATH = os.getenv(
    "DRAFT_INPUTS_VOLUME_PATH",
    "/Volumes/kk_test/sbar_briefing/draft_inputs",
)


def schema() -> str:
    return os.getenv("LAKEBASE_PG_SCHEMA", "sbar")


def create_draft(*, author_email: str, title: str, audience: str, instruction: str) -> str:
    draft_id = str(uuid.uuid4())
    conn = get_connection()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    f'INSERT INTO "{schema()}".drafts '
                    f"(draft_id, author_email, title, audience, instruction, status) "
                    f"VALUES (%s, %s, %s, %s, %s, 'draft')",
                    (draft_id, author_email, title, audience, instruction),
                )
    finally:
        conn.close()
    return draft_id


def get_draft(draft_id: str) -> dict | None:
    rows = query(
        f'SELECT * FROM "{schema()}".drafts WHERE draft_id = %s',
        (draft_id,),
    )
    return rows[0] if rows else None


def list_drafts_for_author(author_email: str, *, include_published: bool = True) -> list[dict]:
    if include_published:
        return query(
            f'SELECT draft_id, title, audience, status, updated_at, published_sbar_id '
            f'FROM "{schema()}".drafts WHERE author_email = %s '
            f"ORDER BY updated_at DESC",
            (author_email,),
        )
    return query(
        f'SELECT draft_id, title, audience, status, updated_at, published_sbar_id '
        f'FROM "{schema()}".drafts '
        f"WHERE author_email = %s AND status != 'published' "
        f"ORDER BY updated_at DESC",
        (author_email,),
    )


def update_draft_fields(draft_id: str, **fields) -> None:
    """Patch arbitrary fields on a draft row. JSON-encoded JSONB columns are
    handled automatically."""
    if not fields:
        return
    json_cols = {"source_files", "corpus_searches"}
    cols = []
    vals = []
    for k, v in fields.items():
        cols.append(f"{k} = %s")
        vals.append(Json(v) if k in json_cols else v)
    cols.append("updated_at = now()")
    sql = f'UPDATE "{schema()}".drafts SET {", ".join(cols)} WHERE draft_id = %s'
    vals.append(draft_id)
    conn = get_connection()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(sql, tuple(vals))
    finally:
        conn.close()


def set_status(draft_id: str, status: str, *, error_message: str | None = None) -> None:
    update_draft_fields(draft_id, status=status, error_message=error_message)


def add_source_file(draft_id: str, filename: str, volume_path: str) -> None:
    """Append a source file entry to the JSONB list. Done as a server-side
    jsonb concat so concurrent uploads from the same draft don't race."""
    entry = {
        "filename": filename,
        "volume_path": volume_path,
        "uploaded_at": datetime.now(timezone.utc).isoformat(),
    }
    conn = get_connection()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    f'UPDATE "{schema()}".drafts '
                    f"SET source_files = source_files || %s::jsonb, updated_at = now() "
                    f"WHERE draft_id = %s",
                    (json.dumps([entry]), draft_id),
                )
    finally:
        conn.close()


def draft_inputs_path(draft_id: str) -> str:
    return f"{DRAFT_INPUTS_VOLUME_PATH}/{draft_id}"
