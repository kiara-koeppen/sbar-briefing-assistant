# Databricks notebook source
# MAGIC %md
# MAGIC # Job: Refresh Knowledge Assistant Index
# MAGIC
# MAGIC Triggered nightly (or by file-arrival) on the supplemental_docs UC volume.
# MAGIC Re-runs `sync_knowledge_sources` so any new or updated documents are picked
# MAGIC up by the KA without manual intervention.
# MAGIC
# MAGIC This is the "closed loop" mechanism: when the SBAR author drops a missing
# MAGIC document into the volume to address a knowledge gap, this job ensures the
# MAGIC KA reflects that change before the next executive question.

# COMMAND ----------

dbutils.widgets.text("ka_display_name", "SBAR Briefing Assistant", "KA Display Name")
KA_NAME = dbutils.widgets.get("ka_display_name")

# COMMAND ----------

import time
from databricks.sdk import WorkspaceClient

w = WorkspaceClient()

ka = None
for k in w.knowledge_assistants.list_knowledge_assistants():
    if k.display_name == KA_NAME:
        ka = k
        break
if ka is None:
    raise RuntimeError(f"KA '{KA_NAME}' not found")

print(f"Refreshing knowledge sources on {ka.display_name} ({ka.endpoint_name})...")
w.knowledge_assistants.sync_knowledge_sources(name=ka.name)

# Wait for the sync to complete (typically 1-3 min for a small corpus).
deadline = time.time() + 600
while time.time() < deadline:
    sources = list(w.knowledge_assistants.list_knowledge_sources(parent=ka.name))
    states = [str(s.state) for s in sources]
    print(f"  sources: {states}")
    if all("UPDATING" not in s for s in states):
        print(f"  Sync complete in {int(time.time() - (deadline - 600))}s.")
        break
    time.sleep(20)
else:
    raise TimeoutError("KA sync did not complete within 10 minutes")
