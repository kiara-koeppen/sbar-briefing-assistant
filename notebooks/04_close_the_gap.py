# Databricks notebook source
# MAGIC %md
# MAGIC # 04 - Close the knowledge gap
# MAGIC
# MAGIC Demo step: the dashboard surfaced one low-confidence answer about the 2023
# MAGIC Joint Commission Site Visit Report. This notebook adds the missing document
# MAGIC to the supplemental corpus and triggers a KA re-index so the next time an
# MAGIC executive asks the same question, the KA has what it needs.
# MAGIC
# MAGIC In production this is automated by a Lakeflow Job (file-trigger on the
# MAGIC supplemental_docs volume). Running this notebook by hand is the demo-flow
# MAGIC equivalent.

# COMMAND ----------

dbutils.widgets.text("catalog", "kk_test", "Catalog")
dbutils.widgets.text("schema", "sbar_briefing", "Schema")
dbutils.widgets.text("supplemental_volume", "supplemental_docs", "Supplemental Docs Volume")
dbutils.widgets.text("ka_display_name", "SBAR Briefing Assistant", "KA Display Name")

CATALOG = dbutils.widgets.get("catalog")
SCHEMA = dbutils.widgets.get("schema")
VOLUME = dbutils.widgets.get("supplemental_volume")
KA_NAME = dbutils.widgets.get("ka_display_name")
PATH = f"/Volumes/{CATALOG}/{SCHEMA}/{VOLUME}"

# COMMAND ----------

# MAGIC %md
# MAGIC ## Add the 2023 Joint Commission report

# COMMAND ----------

REPORT_2023 = """# Joint Commission Site Visit Report — June 2023

**Survey Type:** Mid-cycle Focused Survey (CMS Validation Survey)
**Survey Dates:** June 5-7, 2023
**Outcome:** Accreditation maintained with 2 Requirements for Improvement (RFIs)

## Findings Summary

**Strengths Noted:**
- Continuation of the **structured pharmacist post-discharge callback program** (cited again as exemplary practice)
- Improved hand hygiene compliance vs. 2022 baseline
- New nurse residency program

**Requirements for Improvement:**
1. **MM.05.01.07** - Two instances of high-alert medication storage outside the ADC observed during inpatient unit rounds
2. **PC.01.02.07** - Inconsistent documentation of risk-of-falls reassessment in the post-anesthesia recovery unit

## Discharge Process Observations

The survey team specifically reviewed our discharge protocol and the pharmacist post-discharge callback program. The program was again cited in the surveyor exit summary as a contributor to safe transitions of care, with particular note of the structured callback script logic and direct integration with the medication reconciliation note.

The surveyor explicitly recommended **continuing the program** and noted that **discontinuation could put the system at risk of regression** on transitions-of-care quality measures.

## Plan of Correction

Both RFIs were addressed within the 60-day evidence-of-standards-compliance window. ESC submitted August 2023 and accepted September 2023.

## Surveyor Notes on Quality Programs

The survey team noted that the pharmacist callback program was operating at ~85% callback completion at the time of the survey. The team reviewed the supporting Epic workflow and determined it was effectively integrated with discharge planning.

## Recommendation in Surveyor Exit Summary

> "The structured pharmacist post-discharge callback program represents an exemplary practice in transitions of care. We recommend the organization continue and consider expanding this program. Discontinuation would represent a meaningful step back in the organization's safe-transitions-of-care work and could materially affect readmission rates."

## Next Survey

Triennial survey scheduled for 2025 (estimated June-September 2025 window).
"""

target = f"{PATH}/joint_commission_site_visit_2023.md"
with open(target, "w") as f:
    f.write(REPORT_2023)
print(f"Wrote: {target} ({len(REPORT_2023)} bytes)")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Trigger a KA re-index
# MAGIC
# MAGIC `sync_knowledge_sources` re-scans the bound volume and ingests new files.
# MAGIC In production a Lakeflow Job watches the volume and calls this on file
# MAGIC arrival; the manual call here represents the same trigger.

# COMMAND ----------

from databricks.sdk import WorkspaceClient
import time

w = WorkspaceClient()

ka = None
for k in w.knowledge_assistants.list_knowledge_assistants():
    if k.display_name == KA_NAME:
        ka = k
        break
if ka is None:
    raise RuntimeError(f"KA not found: {KA_NAME}")

print(f"Triggering re-index on {ka.name}...")
w.knowledge_assistants.sync_knowledge_sources(name=ka.name)

# Poll until knowledge source state stabilizes back to UPDATED.
deadline = time.time() + 300
while time.time() < deadline:
    states = []
    for s in w.knowledge_assistants.list_knowledge_sources(parent=ka.name):
        states.append((s.name.split("/")[-1][:8], str(s.state)))
    print(f"  source states: {states}")
    if all("UPDATED" in str(s) and "UPDATING" not in str(s) for _, s in states):
        print("  re-index complete.")
        break
    time.sleep(15)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Verify
# MAGIC
# MAGIC Run this query against the KA after the re-index completes:
# MAGIC
# MAGIC > *What did the Joint Commission say about our discharge protocol in 2023?*
# MAGIC
# MAGIC The KA should now cite `joint_commission_site_visit_2023.md` and return the
# MAGIC surveyor's recommendation that we continue the pharmacist callback program.

# COMMAND ----------

import os
endpoint = ka.endpoint_name
print(f"KA endpoint: {endpoint}")
resp = w.api_client.do(
    "POST",
    f"/serving-endpoints/{endpoint}/invocations",
    body={
        "input": [{"role": "user", "content": "What did the Joint Commission say about our discharge protocol in 2023?"}],
        "max_output_tokens": 700,
    },
)
for item in resp.get("output", []):
    if item.get("type") == "message":
        for c in item.get("content", []):
            if c.get("type") == "output_text":
                print(c.get("text", ""))
