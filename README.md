# Executive SBAR Briefing Assistant

A Databricks-native demo that replaces recurring executive SBAR (Situation,
Background, Assessment, Recommendation) briefing meetings with a self-service
Knowledge Assistant App, complete with full audit telemetry and a closed-loop
improvement view for the SBAR author.

**Live demo URL:** https://sbar-briefing-assistant-669602668219382.2.azure.databricksapps.com

---

## TL;DR

Senior healthcare executives spend hours every two weeks walking peers through
SBAR briefings. Same questions recur, executives can't explore the underlying
evidence between meetings, and there's no audit trail of what concerns
surfaced. This demo collapses that workflow into a self-service experience
with full visibility for the author.

The whole stack runs on Databricks: Agent Bricks Knowledge Assistant +
Databricks App + Lakebase Postgres + Unity Catalog volumes + a Lakeflow Job
keeping the KA index fresh.

## Architecture

```
                                    ┌──────────────────────────┐
                                    │  Unity Catalog (Volumes) │
   ┌─────────────────────┐          │  • sbar_documents        │
   │  SBAR Author (Nina) │ ────────►│  • supplemental_docs     │
   └─────────────────────┘          └────────────┬─────────────┘
                                                 │ grounds
                                                 ▼
                          ┌────────────────────────────────────┐
                          │  Knowledge Assistant (Agent Bricks)│◄────────┐
                          │  ka-3306ffae-endpoint              │         │
                          └────────────────┬───────────────────┘         │
                                           │ Q&A + citations              │
                                           ▼                              │
   ┌─────────────────────┐         ┌──────────────────────────┐          │
   │  Executives (C-suite)│ ──────►│  Databricks App          │          │
   └─────────────────────┘         │  FastAPI + Jinja, OBO    │          │
                                   │  Async KA polling        │          │
                                   └──────────┬───────────────┘          │
                                              │ audit writes              │
                                              ▼                          │
                                   ┌──────────────────────────┐          │
                                   │  Lakebase (Postgres)     │          │
                                   │  sbar_briefing.audit     │          │
                                   │  _events                 │          │
                                   └──────────┬───────────────┘          │
                                              │                          │
                                              ▼                          │
                                   ┌──────────────────────────┐          │
                                   │  Author View             │          │
                                   │  (in-app dashboard)      │          │
                                   └──────────────────────────┘          │
                                                                         │
   ┌───────────────────────────────────────────────────────────────────┐ │
   │  Lakeflow Job: nightly KA reindex on supplemental_docs volume     │─┘
   └───────────────────────────────────────────────────────────────────┘
```

### Components actually built

| Layer | Component | Resource ID |
|---|---|---|
| AI | Agent Bricks Knowledge Assistant | `ka-3306ffae-endpoint` |
| App | Databricks App | `sbar-briefing-assistant` |
| Audit | Lakebase database | `hls-lakebase-demo` (database `sbar_briefing`, schema `sbar`) |
| Storage | UC Volume (SBARs) | `kk_test.sbar_briefing.sbar_documents` |
| Storage | UC Volume (corpus) | `kk_test.sbar_briefing.supplemental_docs` |
| Orchestration | Lakeflow Job (nightly KA refresh) | job_id `966268820122048` |

### Components NOT built (intentional)

- **SDP pipeline (Bronze/Silver/Gold for interaction logs).** The dbdemos
  generator spec called for this, but for a demo with single-digit executives
  and dozens of questions per cycle, an SDP medallion adds no analytical
  value over reading Lakebase directly. The in-app Author View IS the
  analytics layer. SDP would matter at production scale (thousands of
  interactions/day) — not here.
- **Separate AI/BI Lakeview dashboard.** Same reason: the in-app Author View
  already shows engagement KPIs, per-executive breakdown, low-confidence
  flagging, and feedback signals. Building a parallel Lakeview dashboard
  would duplicate work. If a future need calls for surfacing these metrics
  in Databricks One alongside other org-wide dashboards, a small
  Lakebase→Delta sync job + Lakeview JSON would be a 1-day add.

## Demo flow (the one Nina walks through)

1. **Author opens the in-app dashboard** at `/author` and sees:
   - 6 executives viewed the most recent SBAR (the readmission variance one)
   - 14 questions asked across 5 of those execs
   - **1 knowledge gap flagged in amber:** the CFO's "What did the Joint
     Commission say about our discharge protocol in 2023?" returned a
     low-confidence answer.
2. **Author clicks the flagged question** and confirms the KA didn't have a
   2023 Joint Commission report in the corpus.
3. **Author uploads the 2023 report** to the supplemental_docs volume
   (`notebooks/04_close_the_gap.py`).
4. **The Lakeflow Job re-indexes the KA** (or the manual re-index call from
   notebook 04 fires it immediately).
5. **An executive asks the same question** — the KA now cites the 2023 report
   and surfaces the surveyor's recommendation to keep the pharmacist callback
   program.

## Folder structure

```
sbar-briefing-assistant/
├── notebooks/
│   ├── 01_generate_synthetic_content.py      # 4 SBARs + 18 supplemental docs
│   ├── 02_create_knowledge_assistant.py      # KA setup + source binding
│   ├── 03_provision_lakebase_audit.py        # PG database + audit_events + seed data
│   └── 04_close_the_gap.py                   # Demo step: add 2023 report + reindex
├── jobs/
│   └── refresh_ka_index.py                   # Nightly KA reindex job
├── app/
│   ├── main.py                               # FastAPI entry point
│   ├── lib/
│   │   ├── auth.py                           # OBO header parsing (X-Forwarded-*)
│   │   ├── db.py                             # Lakebase Postgres + REST OAuth
│   │   └── ka.py                             # KA Responses API client
│   ├── templates/
│   │   ├── _layout.html
│   │   ├── exec.html                         # SBAR + chat
│   │   └── author.html                       # Author dashboard
│   ├── static/styles.css
│   ├── app.yaml                              # Databricks Apps config
│   └── requirements.txt
└── README.md
```

## Prerequisites

- Databricks workspace (Azure: `adb-669602668219382.2.azuredatabricks.net`)
- Databricks CLI v0.230+
- Local Python 3.11+ with `databricks-sdk>=0.100.0` (for running the
  setup notebooks locally; the Apps runtime SDK is older)
- Unity Catalog enabled
- An existing Lakebase Provisioned instance (`hls-lakebase-demo`) — the demo
  reuses an existing instance to save provisioning time

## Deploy from scratch

The pieces below were built incrementally during the original session.
To redeploy the whole thing:

```bash
# 1. Create catalog/schema/volumes (in the Databricks workspace UI or via SDK)
#    catalog: kk_test
#    schema:  kk_test.sbar_briefing
#    volumes: sbar_documents, supplemental_docs

# 2. Run the setup notebooks (in order)
#    - 01_generate_synthetic_content.py   (writes SBAR markdown + 18 supp docs)
#    - 02_create_knowledge_assistant.py   (creates the KA + source binding, waits for ACTIVE)
#    - 03_provision_lakebase_audit.py     (PG database, audit_events table, seed data)

# 3. Grant the App SP privileges on the sbar Postgres schema
#    (after the App is created so its client_id is known):
#    GRANT USAGE ON SCHEMA sbar TO "<sp_client_id>";
#    GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA sbar TO "<sp_client_id>";
#    ALTER DEFAULT PRIVILEGES IN SCHEMA sbar
#      GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO "<sp_client_id>";

# 4. Upload app source to the workspace and create the App
databricks workspace import-dir ./app /Workspace/Users/$EMAIL/sbar-briefing-assistant/app --profile <profile> --overwrite
databricks apps create sbar-briefing-assistant --source-code-path /Workspace/Users/$EMAIL/sbar-briefing-assistant/app --profile <profile>

# 5. Add resource bindings via the App UI:
#    - serving-endpoint: ka-3306ffae-endpoint (Can Query)
#    - database: hls-lakebase-demo / sbar_briefing (Can connect and create)
#    - volume: kk_test.sbar_briefing.sbar_documents (Read)

# 6. Grant SP READ_VOLUME + USE_CATALOG/USE_SCHEMA via UC
databricks api post /api/2.1/unity-catalog/permissions/volume/kk_test.sbar_briefing.sbar_documents ...

# 7. Create the nightly Lakeflow Job for KA reindex (see jobs/refresh_ka_index.py)
```

## Key design choices

- **OBO via X-Forwarded-* headers; SP never an admin.** Each interaction is
  attributed to the executive's Databricks identity, not to the App SP. The
  SP is granted least-privilege scoped to this demo's resources.
- **Async KA polling, not sync HTTP.** The Databricks Apps proxy times out
  around 60 s on long sync responses. The app dispatches KA calls as FastAPI
  BackgroundTasks and the frontend polls `/api/answer/<question_id>`. Avoids
  the 504.
- **REST fallback for Lakebase credentials.** The Apps runtime SDK lacks
  `w.database`. The app falls back to a direct `POST /api/2.0/database/credentials`
  call. Tokens are cached for ~50 min (they last 1 hr).
- **Files API for volume reads, not filesystem paths.** Apps don't auto-mount
  /Volumes paths even with READ_VOLUME. The app uses `w.files.list_directory_contents`
  and `w.files.download` instead.

## Configuration

App env vars in `app/app.yaml` (most are also overridable via resource bindings):

| Var | Default |
|---|---|
| `KA_ENDPOINT_NAME` | `ka-3306ffae-endpoint` |
| `SBAR_VOLUME_PATH` | `/Volumes/kk_test/sbar_briefing/sbar_documents` |
| `LAKEBASE_INSTANCE` | `hls-lakebase-demo` |
| `LAKEBASE_PG_DATABASE` | `sbar_briefing` |
| `LAKEBASE_PG_SCHEMA` | `sbar` |
| `AUTHOR_USER_EMAILS` | `kiara.koeppen@databricks.com` |

Auto-injected by the Lakebase resource binding: `PGHOST`, `PGDATABASE`,
`PGUSER`, `PGPORT`, `PGSSLMODE`. (`PGPASSWORD` is NOT injected — the app
generates an OAuth token on demand.)

## Comparison to dbdemos generator

This project was built side-by-side with what `dbdemos-generator` produced
for the same prompt. Key differences in approach:

| Decision | dbdemos generator | This build |
|---|---|---|
| Storage of SBAR content | UC volume (markdown) | Same |
| KA grounding | UC volume of supplemental docs | Same |
| App framework | Generated via template | Hand-built FastAPI + Jinja |
| Audit log | SDP Bronze→Silver→Gold to Delta | Lakebase only; in-app analytics |
| Author dashboard | Lakeview AI/BI dashboard | In-app Author View at `/author` |
| KA reindex | Lakeflow Job (file-trigger) | Lakeflow Job (cron schedule) |

Trade-offs:
- dbdemos's SDP + Lakeview path is the "right" architecture at production
  scale, and shows off more Databricks surface area in a customer demo.
- This build is leaner — fewer moving parts, fits the actual data volume,
  and the in-app dashboard renders instantly with no warehouse warm-up.
- For a customer demo where the conversation will land on
  "do we really need the SDP pipeline?" — this build's answer is: no, not
  yet, and here's what you'd add when volume justifies it.
