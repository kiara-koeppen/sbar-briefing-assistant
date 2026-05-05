# Executive SBAR Briefing Assistant

A Databricks-native demo that replaces recurring executive SBAR (Situation,
Background, Assessment, Recommendation) briefing meetings with a self-service
Knowledge Assistant App, complete with full audit telemetry and a closed-loop
improvement view for the SBAR author.

**Live demo URL:** https://sbar-briefing-assistant-669602668219382.2.azure.databricksapps.com

---

> ## Disclaimer
>
> This project is **not an official Databricks product**. It is an unofficial
> demo built by a Databricks employee for educational and customer-walkthrough
> purposes. It is provided **as-is**, with no warranties, no SLA, and no
> implied or expressed support commitment from Databricks.
>
> All sample data in this repository (SBAR contents, supplemental documents,
> KPI numbers, executive personas, contract terms, the "Regional Health System"
> name, etc.) is **synthetic and fictional**. Any resemblance to real
> organizations, individuals, contracts, or clinical situations is
> coincidental.
>
> The code, architecture patterns, and design decisions here are shared
> openly for reference, but customers and partners adopting any of this for
> their own use are responsible for their own security, compliance, privacy,
> and operational reviews. In particular, anyone considering this for use
> with Protected Health Information (PHI) or other regulated data should
> conduct an independent compliance assessment before production rollout.

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

## How it works (the personas)

```
┌─────────────────────────────────────────────────────────────────────┐
│                                                                     │
│  Nina, VP of Operations — the SBAR author                           │
│                                                                     │
│   1. Opens /author/drafts/new                                       │
│   2. Writes a one-paragraph instruction:                            │
│      "Brief the ELT on the readmission spike. Recommend X."         │
│   3. Optionally uploads source PDFs                                 │
│   4. Clicks Generate                                                │
│                                                                     │
│         ▼  agent calls KA, drafts SBAR with cited figures           │
│                                                                     │
│   5. Reviews and edits the draft (auto-saves)                       │
│   6. Optional: Regenerate with edits preserved as context           │
│   7. Clicks Publish                                                 │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              │  SBAR is now visible to executives
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│                                                                     │
│  C-suite executives (CEO, CFO, COO, CMO, CNO, Board Chair)          │
│                                                                     │
│   1. Open the app, see the latest SBAR                              │
│   2. Read the briefing (Situation, Background, Assessment,          │
│      Recommendation)                                                │
│   3. Click any cited source filename to verify it directly          │
│   4. Ask follow-up questions in the chat panel                      │
│   5. KA returns grounded answers with clickable citations           │
│   6. Thumbs up / down feedback                                      │
│                                                                     │
│             ◀────  no meeting required  ────                        │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              │  every interaction logged to Lakebase
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│                                                                     │
│  Nina back at /author — the closed loop                             │
│                                                                     │
│   1. Opens dashboard                                                │
│   2. Sees engagement (who viewed, who asked questions)              │
│   3. Sees knowledge gaps (low-confidence answers flagged in amber)  │
│   4. Drops the missing supporting doc into the UC volume            │
│                                                                     │
│         ▼  Lakeflow Job re-indexes the KA overnight                 │
│                                                                     │
│   5. Next executive question gets the better answer                 │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### One-line summary
Nina drafts an SBAR with an AI assistant that pulls from her organization's
own corpus, executives self-serve through it without a meeting, and Nina sees
exactly what they engaged with and where the AI fell short, so she can close
the gaps before the next briefing cycle.

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

## Deploy via Databricks Asset Bundle

The whole thing is wrapped in a DAB. From a fresh checkout:

### Prerequisites (one-time)
1. **Catalog**. The bundle assumes the catalog already exists (catalogs are
   typically managed at workspace level, not by an app bundle). If yours
   doesn't exist, create it first or update `var.catalog` in `databricks.yml`.
2. **Lakebase instance**. The bundle reuses an existing Lakebase Provisioned
   instance — it doesn't create one. Create one in the workspace UI (CU_1
   tier is fine for the demo) and update `var.lakebase_instance` in
   `databricks.yml` to its name.
3. **CLI profile**. Update `targets.dev.workspace.profile` and
   `targets.prod.workspace.profile` to match your `~/.databrickscfg` profile.

### Deploy
```bash
# Validate first - catches typos before anything hits the workspace.
databricks bundle validate -t prod

# Deploy. Creates schema, volumes, jobs, and the App (without source code yet).
databricks bundle deploy -t prod

# Run the one-shot setup job. Generates synthetic SBARs + supplemental docs,
# creates the Knowledge Assistant, provisions the Lakebase audit table.
# Idempotent - safe to re-run.
databricks bundle run sbar_setup -t prod

# Update KA_ENDPOINT_NAME in app/app.yaml to match the endpoint name
# the setup job created (printed at the end of notebook 02). Then redeploy:
databricks bundle deploy -t prod

# Start the App.
databricks bundle run sbar_briefing_assistant -t prod
```

### Post-deploy: grant Postgres privileges on the audit schema
The DAB binds Lakebase to the App with `CAN_CONNECT_AND_CREATE`. That lets
the App connect, but it doesn't grant access to the existing `sbar` schema.
After the App is created, the App's service principal client_id becomes its
Postgres role name. Run this once (using a Postgres user that owns the schema):

```sql
GRANT USAGE ON SCHEMA sbar TO "<sp_client_id>";
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA sbar TO "<sp_client_id>";
ALTER DEFAULT PRIVILEGES IN SCHEMA sbar
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO "<sp_client_id>";
```

### Switch the nightly KA refresh job from PAUSED to UNPAUSED
The bundle ships the schedule paused so the customer can decide when to
turn it on. In the Jobs UI, open `sbar-briefing-ka-refresh` and resume the
schedule. Or edit `resources/jobs.yml` and set `pause_status: UNPAUSED`.

### Customizing for your workspace
All values are bundle variables in `databricks.yml`. Common changes:

| Variable | What to update |
|---|---|
| `catalog` | Your UC catalog name |
| `lakebase_instance` | Your Lakebase Provisioned instance name |
| `author_emails` | Comma-separated list of SBAR-author emails |
| `app_name` | App name (also affects URL) |

For prod target, set `targets.prod.workspace.root_path` to a deploy location
appropriate for your workspace (the default uses
`${workspace.current_user.userName}` which works for any deployer).

## Production readiness checklist

This is a working prototype that demonstrates the full closed loop. Before a
customer rolls it out for real executive briefings, here's the honest list of
what's built, what's partial, and what would need to be added.

### What's production-grade today
- **OBO auth via X-Forwarded headers.** Each interaction is attributed to the
  executive's Databricks identity, not to the App SP. The SP is granted
  least-privilege scoped permissions.
- **Async KA polling.** Avoids the ~60s Databricks Apps proxy timeout on long
  LLM responses by dispatching as background tasks plus client-side polling.
- **Idempotent setup.** Notebooks 01-05 and the Lakeflow refresh job all
  re-run safely.
- **Bundle-deployable.** `databricks bundle deploy` reproduces every
  resource. Variables for catalog, schema, Lakebase instance, and author
  emails make environment swaps trivial.
- **Audit log.** Every view, question, answer, source citation, feedback
  signal, and authoring action is in a single Lakebase table.
- **Closed-loop knowledge gap detection.** Low-confidence KA answers
  (heuristic + the agent's own "I don't have" language) get flagged in the
  author dashboard and clear out automatically once the missing doc is added
  to the volume.
- **Source verification.** Every cited filename in the SBAR body and in the
  chat is clickable and opens the source doc inline.

### What's partial - works for the demo, needs hardening for production

| Gap | What works today | What's needed for production |
|---|---|---|
| **Source doc access control** | Every executive can see every supplemental doc | Use the executive's OBO token (not the SP's) when serving `/api/source/*` so UC volume permissions apply per-user |
| **Author UI polish** | Functional textarea editor with auto-save | Rich editor with section anchors (one S/B/A/R section per panel), inline diff after regenerate |
| **Generation error handling** | Failures land in `generation_failed` status with the error message | Retry with backoff, partial draft recovery, model fallback |
| **Mobile** | Layout works at desktop sizes | Responsive layout for phones (executives often read briefings on mobile) |
| **Multi-author** | One author email at a time | Per-author SBAR list view, ownership filters, author-level permissions |

### What's NOT built - decide with the customer

| Thing | What it is | When you'd add it |
|---|---|---|
| **Versioning** | If Nina edits a published SBAR, keep history | If briefings get amended after publish |
| **Search/filter** | Across the SBAR list | Once the corpus passes ~20-30 SBARs |
| **Identity outside Databricks** | Today the app uses Databricks workspace identity | If executives aren't workspace users; integrate Microsoft Entra or whatever IdP is in place |
| **Slides export** | Render an SBAR as a slide deck | If the customer's executives prefer slides over text |
| **PHI redaction or masking** | Manual review today | If the SBAR is healthcare with real patient data, layer in a redaction pass before publish |
| **Audit retention policy** | Lakebase table grows unbounded | Set a TTL (e.g. partition by month, archive >12 months to Delta) |
| **Production telemetry analytics** | In-app dashboard reads Lakebase directly | At scale (thousands of interactions/day), add an SDP medallion: Bronze (Lakebase sync), Silver, Gold + AI/BI Lakeview dashboard |

### Suggested first-week production hardening (if customer wants to ship)

✅ **Done in this build:**
- **PDF source ingestion.** `pypdf` extracts text from PDF uploads in
  `lib/llm.py` so authors can drag in any source format the org already has.
- **Publish notifications.** `lib/notify.py` sends a Slack-formatted webhook
  on publish (set `NOTIFICATION_SLACK_WEBHOOK_URL` in `app.yaml` to wire it
  to a real Slack/Teams channel). Falls back to log-only if unconfigured.
  Each notification attempt is recorded as a `notification_sent` event in
  the audit table, so the author can see in the dashboard that publish
  triggered the broadcast.

🔧 **Still to do for a real rollout:**

1. Wire `/api/source/*` to use the executive's OBO token rather than the
   SP for volume reads. ~30 min of code change. Until this lands, every
   exec sees every supplemental doc regardless of UC permissions.
2. Set a Lakebase audit retention policy (partition by month, archive
   monthly via a job). ~2 hours.
3. Decide PHI/compliance posture with the customer's compliance team. Output
   is a one-pager: what data classes are allowed in volumes, what redaction
   happens at draft time, who approves before publish, audit retention.
   Time depends on the customer's existing data classification policy.

That's roughly a half-day of code plus a compliance conversation to get
from "live demo" to "defensible production rollout for a single team of
executives."

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
