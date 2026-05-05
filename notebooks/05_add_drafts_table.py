# Databricks notebook source
# MAGIC %md
# MAGIC # 05 - Add drafts table to Lakebase
# MAGIC
# MAGIC Migration step. Adds the `sbar.drafts` table that powers the auto-SBAR
# MAGIC drafting workflow. Idempotent — uses `CREATE TABLE IF NOT EXISTS`.
# MAGIC
# MAGIC ## Schema
# MAGIC
# MAGIC | Column | Type | Description |
# MAGIC |---|---|---|
# MAGIC | `draft_id` | UUID PK | |
# MAGIC | `author_email` | TEXT | Who is drafting |
# MAGIC | `title` | TEXT | Working title |
# MAGIC | `audience` | TEXT | e.g., "Executive Leadership Team" |
# MAGIC | `instruction` | TEXT | Author's natural-language brief for the LLM |
# MAGIC | `source_files` | JSONB | List of `{filename, volume_path}` from draft_inputs |
# MAGIC | `current_md` | TEXT | The latest draft markdown (incl. author edits) |
# MAGIC | `corpus_searches` | JSONB | Tool-call audit from the agentic generation |
# MAGIC | `status` | TEXT | `draft`, `generating`, `published` |
# MAGIC | `created_at`, `updated_at` | TIMESTAMPTZ | |
# MAGIC | `published_at` | TIMESTAMPTZ | When it shipped to sbar_documents |
# MAGIC | `published_sbar_id` | TEXT | Filename in sbar_documents after publish |

# COMMAND ----------

dbutils.widgets.text("lakebase_instance", "hls-lakebase-demo", "Lakebase instance")
dbutils.widgets.text("pg_database", "sbar_briefing", "Postgres database")
dbutils.widgets.text("pg_schema", "sbar", "Postgres schema")

LAKEBASE_INSTANCE = dbutils.widgets.get("lakebase_instance")
PG_DATABASE = dbutils.widgets.get("pg_database")
PG_SCHEMA = dbutils.widgets.get("pg_schema")

# COMMAND ----------

# MAGIC %pip install --quiet psycopg2-binary
# MAGIC dbutils.library.restartPython()

# COMMAND ----------

import uuid
import psycopg2
from databricks.sdk import WorkspaceClient

w = WorkspaceClient()
inst = w.database.get_database_instance(name=LAKEBASE_INSTANCE)
HOST = inst.read_write_dns
USER = w.current_user.me().user_name
cred = w.database.generate_database_credential(
    request_id=f"sbar-drafts-migrate-{uuid.uuid4().hex[:8]}",
    instance_names=[LAKEBASE_INSTANCE],
)
TOKEN = cred.token

conn = psycopg2.connect(host=HOST, port=5432, user=USER, password=TOKEN,
                        database=PG_DATABASE, sslmode="require")
conn.autocommit = True
cur = conn.cursor()

cur.execute(f"""
CREATE TABLE IF NOT EXISTS "{PG_SCHEMA}".drafts (
    draft_id          UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    author_email      TEXT         NOT NULL,
    title             TEXT,
    audience          TEXT,
    instruction       TEXT,
    source_files      JSONB        NOT NULL DEFAULT '[]'::jsonb,
    current_md        TEXT,
    corpus_searches   JSONB        NOT NULL DEFAULT '[]'::jsonb,
    status            TEXT         NOT NULL DEFAULT 'draft'
                      CHECK (status IN ('draft','generating','generation_failed','published')),
    error_message     TEXT,
    created_at        TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ  NOT NULL DEFAULT now(),
    published_at      TIMESTAMPTZ,
    published_sbar_id TEXT
);
""")

cur.execute(f'CREATE INDEX IF NOT EXISTS drafts_author_idx ON "{PG_SCHEMA}".drafts(author_email, updated_at DESC);')
cur.execute(f'CREATE INDEX IF NOT EXISTS drafts_status_idx ON "{PG_SCHEMA}".drafts(status, updated_at DESC);')

cur.execute(f"SELECT count(*) FROM \"{PG_SCHEMA}\".drafts;")
print(f"drafts table ready. Existing rows: {cur.fetchone()[0]}")

# Grant the App SP access (the role name matches its client_id)
SP_CLIENT_ID = "bb0d7570-81c7-4f2e-a049-aece71517762"
try:
    cur.execute(f'GRANT SELECT, INSERT, UPDATE, DELETE ON "{PG_SCHEMA}".drafts TO "{SP_CLIENT_ID}";')
    print(f"Granted DML on drafts to {SP_CLIENT_ID}")
except Exception as e:
    print(f"Grant skipped (role may not exist yet): {e}")

cur.close(); conn.close()
