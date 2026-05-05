# Databricks notebook source
# MAGIC %md
# MAGIC # 03 - Provision Lakebase audit schema + seed exec interaction history
# MAGIC
# MAGIC Creates the `sbar_briefing` Postgres database on the existing Lakebase
# MAGIC instance, the `sbar.audit_events` table, and seeds simulated C-suite
# MAGIC interactions for the demo.
# MAGIC
# MAGIC ## Audit event shape
# MAGIC
# MAGIC One row per discrete interaction. `payload` JSONB carries event-specific
# MAGIC fields. Event types:
# MAGIC - `view`     — exec opened the SBAR (`payload.duration_minutes`)
# MAGIC - `question` — exec asked a question (`payload.question`, `payload.question_id`)
# MAGIC - `answer`   — KA returned answer (`payload.question_id`, `payload.answer`,
# MAGIC                `payload.sources`, `payload.low_confidence`)
# MAGIC - `feedback` — exec rated the answer (`payload.question_id`, `payload.rating`)
# MAGIC
# MAGIC ## Why Lakebase
# MAGIC The app writes one row per UI interaction and the Author dashboard reads
# MAGIC engagement aggregates with sub-second latency. Lakebase Postgres handles both
# MAGIC patterns far better than direct Delta writes from a low-volume web app.

# COMMAND ----------

dbutils.widgets.text("lakebase_instance", "hls-lakebase-demo", "Lakebase instance name")
dbutils.widgets.text("pg_database", "sbar_briefing", "Postgres database name")
dbutils.widgets.text("pg_schema", "sbar", "Postgres schema name")
dbutils.widgets.dropdown("seed_data", "true", ["true", "false"], "Seed simulated interaction history")

LAKEBASE_INSTANCE = dbutils.widgets.get("lakebase_instance")
PG_DATABASE = dbutils.widgets.get("pg_database")
PG_SCHEMA = dbutils.widgets.get("pg_schema")
SEED = dbutils.widgets.get("seed_data") == "true"

# COMMAND ----------

# MAGIC %pip install --quiet psycopg2-binary
# MAGIC dbutils.library.restartPython()

# COMMAND ----------

import json, uuid
from datetime import datetime, timezone, timedelta
import psycopg2
from psycopg2.extras import Json
from databricks.sdk import WorkspaceClient

w = WorkspaceClient()
inst = w.database.get_database_instance(name=LAKEBASE_INSTANCE)
HOST = inst.read_write_dns
USER = w.current_user.me().user_name
print(f"Lakebase host: {HOST}")
print(f"User: {USER}")

cred = w.database.generate_database_credential(
    request_id=f"sbar-setup-{uuid.uuid4().hex[:8]}",
    instance_names=[LAKEBASE_INSTANCE],
)
TOKEN = cred.token

# COMMAND ----------

# MAGIC %md
# MAGIC ## Create Postgres database (if missing)

# COMMAND ----------

admin_conn = psycopg2.connect(host=HOST, port=5432, user=USER, password=TOKEN,
                              database="databricks_postgres", sslmode="require")
admin_conn.autocommit = True
ac = admin_conn.cursor()
ac.execute("SELECT 1 FROM pg_database WHERE datname = %s", (PG_DATABASE,))
if ac.fetchone() is None:
    ac.execute(f'CREATE DATABASE "{PG_DATABASE}"')
    print(f"Created database: {PG_DATABASE}")
else:
    print(f"Database {PG_DATABASE} already exists")
ac.close(); admin_conn.close()

# COMMAND ----------

# MAGIC %md
# MAGIC ## Schema and audit_events table

# COMMAND ----------

conn = psycopg2.connect(host=HOST, port=5432, user=USER, password=TOKEN,
                        database=PG_DATABASE, sslmode="require")
conn.autocommit = True
cur = conn.cursor()

cur.execute(f'CREATE SCHEMA IF NOT EXISTS "{PG_SCHEMA}";')
cur.execute(f"""
CREATE TABLE IF NOT EXISTS "{PG_SCHEMA}".audit_events (
    event_id      UUID         DEFAULT gen_random_uuid() PRIMARY KEY,
    user_email    TEXT         NOT NULL,
    user_role     TEXT,
    session_id    TEXT         NOT NULL,
    sbar_id       TEXT,
    event_type    TEXT         NOT NULL CHECK (event_type IN ('view','question','answer','feedback')),
    payload       JSONB        NOT NULL,
    ts            TIMESTAMPTZ  NOT NULL DEFAULT now()
);
""")
cur.execute(f'CREATE INDEX IF NOT EXISTS audit_events_user_ts_idx ON "{PG_SCHEMA}".audit_events(user_email, ts DESC);')
cur.execute(f'CREATE INDEX IF NOT EXISTS audit_events_sbar_ts_idx ON "{PG_SCHEMA}".audit_events(sbar_id, ts DESC);')
cur.execute(f'CREATE INDEX IF NOT EXISTS audit_events_type_ts_idx ON "{PG_SCHEMA}".audit_events(event_type, ts DESC);')

cur.execute(f"SELECT count(*) FROM \"{PG_SCHEMA}\".audit_events;")
existing_count = cur.fetchone()[0]
print(f"Existing rows: {existing_count}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Seed simulated interaction history (5 of 6 execs viewed)

# COMMAND ----------

if not SEED:
    print("Seeding skipped (seed_data=false).")
    cur.close(); conn.close()
    dbutils.notebook.exit("ok")

SBAR_ID = "sbar_2025_q4_06_readmission_variance"

EXECS = [
    {"email": "ceo@regionalhealth.example.com",  "role": "CEO"},
    {"email": "cfo@regionalhealth.example.com",  "role": "CFO"},
    {"email": "coo@regionalhealth.example.com",  "role": "COO"},
    {"email": "cmo@regionalhealth.example.com",  "role": "CMO"},
    {"email": "cno@regionalhealth.example.com",  "role": "CNO"},
    {"email": "board.chair@regionalhealth.example.com", "role": "Board Chair"},
]

NOW = datetime.now(timezone.utc)
SBAR_PUBLISHED = NOW - timedelta(hours=48)

INTERACTIONS = [
    {"user": EXECS[0], "view_offset_hours": 4, "session_dur_min": 18, "questions": [
        {"q": "What's the projected financial impact if we don't restore the pharmacist callback workflow?",
         "a": "Estimated $1.8M in CMS readmission penalties for FY26 plus avoided readmission costs. Per the prior SBAR pilot results, restoring the workflow with 2 additional FTE clinical pharmacists projects $2.4M in annual avoided cost.",
         "sources": ["sbar_2025_q4_06_readmission_variance.md","pharmacy_callback_pilot_results_2022.md","kpi_dashboard_export_q3_2025.md"],
         "feedback": "up"},
        {"q": "Have we tried the nurse home visit pilot before?",
         "a": "No, the 2022 pilot was a pharmacist-led callback program. The Care Management RN positions needed for the home visit pilot are unfilled per the Q4 staffing plan.",
         "sources": ["pharmacy_callback_pilot_results_2022.md","nursing_staffing_plan_q4.md"],
         "feedback": "up"},
        {"q": "When does Anthem expire?",
         "a": "December 31, 2025. The recommended counter is 6.5% with a 3-year term plus a value-based addendum.",
         "sources": ["sbar_2025_q4_04_anthem_contract.md","anthem_contract_2023_2025_terms.md"],
         "feedback": None},
    ]},
    {"user": EXECS[1], "view_offset_hours": 6, "session_dur_min": 22, "questions": [
        {"q": "What did the Joint Commission say about our discharge protocol in 2023?",
         "a": "I don't have a 2023 Joint Commission Site Visit Report in the supplemental materials. The 2022 report is available and noted the structured pharmacist callback program as exemplary. To answer this question, the 2023 report would need to be added to the corpus.",
         "sources": ["joint_commission_site_visit_2022.md"],
         "feedback": "down", "low_confidence": True},
        {"q": "What is our current case-mix index trend?",
         "a": "Q3 2025 CMI is 1.78, up from 1.67 at Anthem contract signing in 2022 — a 6.4% increase that supports the requested rate increase.",
         "sources": ["kpi_dashboard_export_q3_2025.md","anthem_contract_2023_2025_terms.md"],
         "feedback": "up"},
        {"q": "How much does the Joint Commission program contribute to our quality metrics?",
         "a": "The pharmacist callback program was cited in the 2022 Joint Commission survey as exemplary. Without the 2023 site visit report I cannot speak to the current cycle.",
         "sources": ["pharmacy_callback_pilot_results_2022.md","joint_commission_site_visit_2022.md"],
         "feedback": None},
    ]},
    {"user": EXECS[2], "view_offset_hours": 8, "session_dur_min": 14, "questions": [
        {"q": "What's driving the readmission variance vs Q3?",
         "a": "Two operational changes from October 2025: (1) the Epic 2025.1 upgrade deprecated the pharmacist callback workflow (callback completion dropped from 87% to 47%), and (2) the CHF Discharge Protocol v3.2 reduced the inpatient pharmacy consult from 30 to 15 minutes. Patients receiving callbacks had a 9.1% readmission rate vs 21.3% for those who did not.",
         "sources": ["sbar_2025_q4_06_readmission_variance.md","ehr_upgrade_project_charter_2025.md","chf_discharge_protocol_v3_2.md","pharmacist_productivity_report.md"],
         "feedback": "up"},
        {"q": "Why is the 2022 pilot not still running?",
         "a": "Discontinued in Q3 2023 during a pharmacy department staffing reorganization. The Epic workflow remained but utilization declined to ~40% by mid-2024. The 2025.1 upgrade then deprecated the legacy module entirely.",
         "sources": ["pharmacy_callback_pilot_results_2022.md","ehr_upgrade_project_charter_2025.md"],
         "feedback": "up"},
    ]},
    {"user": EXECS[3], "view_offset_hours": 12, "session_dur_min": 16, "questions": [
        {"q": "How does this affect our CMS Star Rating?",
         "a": "The Care Coordination measure is at 78% in Q3 vs the 4-star threshold of 82%, driven by the same pharmacist workflow issue. Three other measures are also below threshold. Mid-cycle 2026 projection drops the system from 4 stars to 3 stars without intervention.",
         "sources": ["cms_star_ratings_history.md","hedis_measure_performance_q3_2025.md","sbar_2025_q4_03_cms_star_measures.md"],
         "feedback": "up"},
        {"q": "What's the patient satisfaction impact?",
         "a": "Press Ganey communication-about-medicines top-box dropped from 64% to 60% in Q3, and care transition top-box dropped from 51% to 49%. Restoration of the callback program is expected to lift both domains.",
         "sources": ["patient_satisfaction_press_ganey_q3.md","pharmacist_productivity_report.md"],
         "feedback": "up"},
    ]},
    {"user": EXECS[4], "view_offset_hours": 18, "session_dur_min": 11, "questions": [
        {"q": "Do we have the nursing capacity for the 7-day home visit pilot?",
         "a": "Not currently. The Care Management team has 3 RN vacancies open as of Q4 2025. Those vacancies are blocking the pilot launch as designed.",
         "sources": ["nursing_staffing_plan_q4.md","sbar_2025_q4_06_readmission_variance.md"],
         "feedback": "up"},
    ]},
]

events = []
for inter in INTERACTIONS:
    user = inter["user"]
    session_id = str(uuid.uuid4())
    view_ts = SBAR_PUBLISHED + timedelta(hours=inter["view_offset_hours"])
    events.append({"user_email": user["email"], "user_role": user["role"],
                   "session_id": session_id, "sbar_id": SBAR_ID,
                   "event_type": "view", "payload": {"duration_minutes": inter["session_dur_min"]},
                   "ts": view_ts})
    for i, q in enumerate(inter["questions"]):
        q_ts = view_ts + timedelta(minutes=2 + i * 4)
        a_ts = q_ts + timedelta(seconds=8)
        qid = str(uuid.uuid4())
        events.append({"user_email": user["email"], "user_role": user["role"],
                       "session_id": session_id, "sbar_id": SBAR_ID, "event_type": "question",
                       "payload": {"question": q["q"], "question_id": qid}, "ts": q_ts})
        events.append({"user_email": user["email"], "user_role": user["role"],
                       "session_id": session_id, "sbar_id": SBAR_ID, "event_type": "answer",
                       "payload": {"question_id": qid, "answer": q["a"], "sources": q["sources"],
                                   "low_confidence": q.get("low_confidence", False)}, "ts": a_ts})
        if q.get("feedback"):
            events.append({"user_email": user["email"], "user_role": user["role"],
                           "session_id": session_id, "sbar_id": SBAR_ID, "event_type": "feedback",
                           "payload": {"question_id": qid, "rating": q["feedback"]},
                           "ts": a_ts + timedelta(seconds=15)})

cur.execute(f'DELETE FROM "{PG_SCHEMA}".audit_events;')
print("Cleared existing events.")

for e in events:
    cur.execute(f"""
        INSERT INTO "{PG_SCHEMA}".audit_events
            (user_email, user_role, session_id, sbar_id, event_type, payload, ts)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
    """, (e["user_email"], e["user_role"], e["session_id"], e["sbar_id"],
          e["event_type"], Json(e["payload"]), e["ts"]))

cur.execute(f"SELECT count(*), event_type FROM \"{PG_SCHEMA}\".audit_events GROUP BY event_type ORDER BY event_type;")
print("Counts by event type:")
for cnt, t in cur.fetchall():
    print(f"  {t}: {cnt}")

cur.close(); conn.close()
print(f"\nSeeded {len(events)} simulated interaction events.")
