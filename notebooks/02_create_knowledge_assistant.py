# Databricks notebook source
# MAGIC %md
# MAGIC # 02 - Create Knowledge Assistant (Agent Bricks KA)
# MAGIC
# MAGIC Provisions the Agent Bricks Knowledge Assistant and adds the `supplemental_docs`
# MAGIC volume as its knowledge source.
# MAGIC
# MAGIC ## Output
# MAGIC - KA endpoint name (use as `ka_endpoint` parameter throughout the rest of the demo)
# MAGIC - KA id and full resource name
# MAGIC
# MAGIC ## Notes
# MAGIC - The KA goes through `CREATING` → `ONLINE` (typically 2-5 minutes).
# MAGIC - The knowledge source goes through `UPDATING` → `READY` as it indexes the volume.
# MAGIC - Re-running this notebook updates the KA in place rather than creating a duplicate
# MAGIC   (keyed off the `display_name`).

# COMMAND ----------

dbutils.widgets.text("catalog", "kk_test", "Catalog")
dbutils.widgets.text("schema", "sbar_briefing", "Schema")
dbutils.widgets.text("supplemental_volume", "supplemental_docs", "Supplemental Docs Volume")
dbutils.widgets.text("ka_display_name", "SBAR Briefing Assistant", "KA Display Name")

CATALOG = dbutils.widgets.get("catalog")
SCHEMA = dbutils.widgets.get("schema")
SUPP_VOLUME = dbutils.widgets.get("supplemental_volume")
KA_DISPLAY_NAME = dbutils.widgets.get("ka_display_name")

VOLUME_PATH = f"/Volumes/{CATALOG}/{SCHEMA}/{SUPP_VOLUME}"

# COMMAND ----------

from databricks.sdk import WorkspaceClient
from databricks.sdk.service import knowledgeassistants as ka

w = WorkspaceClient()

# COMMAND ----------

# MAGIC %md
# MAGIC ## Find or create the KA

# COMMAND ----------

KA_INSTRUCTIONS = """You are an executive briefing assistant for a regional healthcare system. You answer follow-up questions from C-suite executives about SBAR (Situation, Background, Assessment, Recommendation) briefings authored by the VP of Operations.

Always cite specific documents and figures from the supplemental corpus. Be concise and direct. Distinguish between data you can verify from the corpus vs. inferences. If you don't have the data, say so explicitly rather than guessing.

Reference prior SBARs and pilot results when an executive asks "have we tried this before?" When asked about financial impact, contract terms, or staffing decisions, surface the underlying numbers from the KPI and operational reports.

Tone: professional, brief, evidence-based. Do not over-explain basic terms. The glossary document covers domain abbreviations.

If a question cannot be answered from the supplemental materials, say so plainly and identify what document would be needed. Do NOT speculate or invent figures."""

KA_DESCRIPTION = "Knowledge Assistant for the Executive SBAR Briefing demo. Grounded on supplemental healthcare materials so executives can ask follow-up questions on SBAR briefings without holding a meeting."

existing = None
for k in w.knowledge_assistants.list_knowledge_assistants():
    if k.display_name == KA_DISPLAY_NAME:
        existing = k
        break

if existing:
    print(f"Found existing KA: {existing.name} (state={existing.state})")
    ka_obj = existing
else:
    ka_obj = w.knowledge_assistants.create_knowledge_assistant(
        knowledge_assistant=ka.KnowledgeAssistant(
            display_name=KA_DISPLAY_NAME,
            description=KA_DESCRIPTION,
            instructions=KA_INSTRUCTIONS,
        )
    )
    print(f"Created KA: {ka_obj.name} (state={ka_obj.state})")

print(f"  endpoint_name: {ka_obj.endpoint_name}")
print(f"  experiment_id: {ka_obj.experiment_id}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Add the supplemental docs volume as a knowledge source

# COMMAND ----------

existing_source = None
for s in w.knowledge_assistants.list_knowledge_sources(parent=ka_obj.name):
    if s.files and s.files.path == VOLUME_PATH:
        existing_source = s
        break

if existing_source:
    print(f"Found existing source: {existing_source.name} (state={existing_source.state})")
else:
    source = w.knowledge_assistants.create_knowledge_source(
        parent=ka_obj.name,
        knowledge_source=ka.KnowledgeSource(
            display_name="SBAR Supplemental Materials",
            description="KPI exports, board memos, prior SBARs, contract terms, policy docs, prior pilot results, glossary",
            source_type="FILES",
            files=ka.FilesSpec(path=VOLUME_PATH),
        ),
    )
    print(f"Created source: {source.name} (state={source.state})")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Wait for the KA to come online

# COMMAND ----------

import time

start = time.time()
while True:
    current = w.knowledge_assistants.get_knowledge_assistant(name=ka_obj.name)
    elapsed = int(time.time() - start)
    print(f"[{elapsed}s] KA state: {current.state}")
    if current.state == ka.KnowledgeAssistantState.ONLINE:
        print(f"KA is ONLINE. Endpoint: {current.endpoint_name}")
        break
    if current.state == ka.KnowledgeAssistantState.OFFLINE:
        raise RuntimeError(f"KA went OFFLINE: {current.error_info}")
    if elapsed > 600:
        raise TimeoutError("KA did not come online within 10 minutes")
    time.sleep(15)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Output the endpoint name for downstream notebooks/app

# COMMAND ----------

dbutils.notebook.exit(current.endpoint_name)
