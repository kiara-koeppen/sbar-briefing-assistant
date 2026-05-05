# Executive SBAR Briefing Assistant

A Databricks-native demo that replaces recurring executive SBAR (Situation, Background, Assessment, Recommendation) briefing meetings with a self-service Knowledge Assistant App, complete with full audit telemetry and a closed-loop improvement dashboard for the SBAR author.

## Why this exists

Senior healthcare executives spend hours every two weeks walking peers through SBAR briefings. Same questions recur, executives can't explore the underlying evidence between meetings, and there's no audit trail of what concerns surfaced. This demo shows how Databricks (Knowledge Assistant + Apps + Lakebase + UC + AI/BI) collapses that workflow into a self-service experience with full visibility for the author.

## Architecture

```
                                    ┌──────────────────────────┐
                                    │  Unity Catalog (Volumes) │
                                    │  • sbar_documents        │
   ┌─────────────────────┐          │  • supplemental_docs     │
   │  SBAR Author (Nina) │ ────────►│                          │
   └─────────────────────┘          └────────────┬─────────────┘
                                                 │
                                                 │ grounds
                                                 ▼
                          ┌────────────────────────────────────┐
                          │  Knowledge Assistant (Agent Bricks)│
                          └────────────────┬───────────────────┘
                                           │
                                           │ Q&A + citations
                                           ▼
   ┌─────────────────────┐         ┌──────────────────────────┐         ┌─────────────────────┐
   │  Executives (C-suite)│ ──────►│  Databricks App          │ ───────►│  Lakebase (Postgres)│
   └─────────────────────┘         │  (FastAPI + React, OBO)  │  audit  │  audit_events table │
                                   └──────────┬───────────────┘  writes └──────────┬──────────┘
                                              │                                    │
                                              │ MLflow Tracing                     │ sync
                                              ▼                                    ▼
                                                                          ┌──────────────────┐
                                                                          │ SDP Pipeline     │
                                                                          │ Bronze → Silver  │
                                                                          │     → Gold       │
                                                                          └────────┬─────────┘
                                                                                   │
                                                                                   ▼
                                                                          ┌──────────────────┐
                                                                          │ AI/BI Dashboard  │
                                                                          │ (Author View)    │
                                                                          └──────────────────┘

   ┌──────────────────────────────────────────────────────────────────────────────────────┐
   │  Lakeflow Job — file-trigger on supplemental_docs volume → refresh KA index nightly  │
   └──────────────────────────────────────────────────────────────────────────────────────┘
```

## Components

| Layer | Component | Purpose |
|-------|-----------|---------|
| Storage | UC Volumes | SBAR markdown + supplemental PDFs/docs |
| AI | Agent Bricks Knowledge Assistant | Grounded Q&A with citations |
| App | Databricks App (FastAPI + React) | SBAR rendering, chat UI, audit logging, OBO auth |
| Audit | Lakebase (Postgres) | High-frequency interaction writes |
| Analytics | SDP Pipeline | Bronze → Silver → Gold for dashboard |
| BI | AI/BI Lakeview Dashboard | SBAR author engagement view |
| Orchestration | Lakeflow Job | KA index refresh on doc changes |
| Governance | Unity Catalog | Single permission model, MLflow Tracing for KA calls |

## Prerequisites

- Databricks workspace (Azure: `adb-669602668219382.2.azuredatabricks.net`)
- Databricks CLI v0.230+
- Python 3.11+
- Node 20+ (for the React frontend)
- Unity Catalog enabled
- Permissions: workspace admin or sufficient grants to create catalogs, volumes, KAs, Lakebase instances, apps, and jobs

## Folder structure

```
sbar-briefing-assistant/
├── notebooks/         # Catalog/volume setup, synthetic data gen, KA setup
├── app/
│   ├── backend/       # FastAPI app: KA proxy, audit logging, OBO auth
│   └── frontend/      # React app: SBAR rendering + chat
├── pipelines/         # Spark Declarative Pipeline for interaction logs
├── jobs/              # Lakeflow Job definitions (KA index refresh)
├── dashboards/        # Lakeview dashboard JSON
├── data/              # Local synthetic data templates
└── bundle/            # Databricks Asset Bundle (final deploy artifact)
```

## How to deploy and run

(Filled in as the build progresses.)

## Configuration

All notebooks parameterized via `dbutils.widgets`:
- `catalog` (default: `kk_test`)
- `schema` (default: `sbar_briefing`)
- `sbar_volume` (default: `sbar_documents`)
- `supplemental_volume` (default: `supplemental_docs`)
- `ka_endpoint` (set after KA creation)
- `lakebase_instance` (set after Lakebase provisioning)

## Notes

- KA calls use async transport (background job + polling), not sync HTTP, to avoid the 504 timeout on the Databricks Apps proxy.
- App uses OBO via `X-Forwarded-Access-Token` for user identity; SP is never made an admin.
- Final state will be packaged as a Databricks Asset Bundle for one-command redeploy.
