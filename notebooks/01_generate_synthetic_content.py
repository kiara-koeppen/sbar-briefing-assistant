# Databricks notebook source
# MAGIC %md
# MAGIC # 01 - Generate Synthetic SBAR Content + Supplemental Docs
# MAGIC
# MAGIC Populates the two UC volumes with realistic healthcare SBAR briefings and a
# MAGIC supporting corpus that the Knowledge Assistant will ground on.
# MAGIC
# MAGIC ## What gets created
# MAGIC
# MAGIC **`sbar_documents` volume** (4 SBAR briefings as markdown):
# MAGIC 1. Q4 Hospital Readmission Variance (the primary demo SBAR)
# MAGIC 2. ED Throughput Improvement Initiative
# MAGIC 3. Anthem Payer Contract Renegotiation Status
# MAGIC 4. CMS Star Quality Measure Performance
# MAGIC
# MAGIC **`supplemental_docs` volume** (~17 grounding docs as markdown):
# MAGIC - KPI exports, board memos, prior SBARs, policy docs, contract terms
# MAGIC - **Intentionally excluded:** Joint Commission 2023 Site Visit Report — this is
# MAGIC   the document the demo storyline says is missing. Notebook 04 uploads it after
# MAGIC   the dashboard surfaces the gap.
# MAGIC
# MAGIC ## How to run
# MAGIC
# MAGIC Attach to a serverless notebook compute (or a small interactive cluster) and
# MAGIC run all. Idempotent — overwrites the volume contents on each run.

# COMMAND ----------

# MAGIC %md
# MAGIC ## Parameters

# COMMAND ----------

dbutils.widgets.text("catalog", "kk_test", "Catalog")
dbutils.widgets.text("schema", "sbar_briefing", "Schema")
dbutils.widgets.text("sbar_volume", "sbar_documents", "SBAR Volume")
dbutils.widgets.text("supplemental_volume", "supplemental_docs", "Supplemental Docs Volume")

CATALOG = dbutils.widgets.get("catalog")
SCHEMA = dbutils.widgets.get("schema")
SBAR_VOLUME = dbutils.widgets.get("sbar_volume")
SUPP_VOLUME = dbutils.widgets.get("supplemental_volume")

SBAR_PATH = f"/Volumes/{CATALOG}/{SCHEMA}/{SBAR_VOLUME}"
SUPP_PATH = f"/Volumes/{CATALOG}/{SCHEMA}/{SUPP_VOLUME}"

print(f"SBAR volume: {SBAR_PATH}")
print(f"Supplemental volume: {SUPP_PATH}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## SBAR documents
# MAGIC
# MAGIC Each SBAR follows the standard healthcare format:
# MAGIC **S**ituation - **B**ackground - **A**ssessment - **R**ecommendation.

# COMMAND ----------

SBAR_README = """# Hospital Readmission Variance — Q4 2025

**Author:** Nina Patel, VP of Operations
**Date:** December 1, 2025
**Audience:** Executive Leadership Team
**Briefing Cycle:** Q4 2025 #6

## Situation
30-day all-cause readmission rate climbed to **17.2%** in November, up from a Q3 baseline of 14.8% and well above the 14.5% target set in the Q1 strategic plan. The variance is concentrated in the CHF and COPD discharge cohorts — CHF readmissions are at 22.1% (target: 18%), COPD at 19.4% (target: 17%).

Financial impact at the current run rate: estimated **$1.8M in CMS readmission penalties** for FY26 if the trend continues into Q1.

## Background
The shift correlates with two operational changes that landed in October 2025:

1. **EHR upgrade (Epic version 2025.1).** The discharge module was reconfigured, and the existing pharmacist post-discharge callback workflow was inadvertently deprecated during the migration. Callback completion dropped from 87% pre-upgrade to 47% post-upgrade.
2. **Discharge protocol revision (CHF Discharge Protocol v3.2).** The revised protocol shortened the inpatient pharmacy consult from 30 minutes to 15 minutes for stable CHF patients. Reasoning at the time: clinical pharmacist capacity constraints.

A similar pilot was run in Q1 2022 (see *Pharmacy Callback Program Pilot Results 2022*) and demonstrated a 3.1 percentage-point reduction in 30-day CHF readmissions. That pilot was discontinued in Q3 2023 due to staffing reorganization.

## Assessment
The data strongly suggests the readmission spike is attributable to the loss of pharmacist post-discharge engagement, not to the EHR upgrade itself or to underlying patient acuity:

- Patient-mix-adjusted readmission rate shows the same magnitude of variance as the unadjusted rate.
- Cohort analysis: patients who received a successful pharmacist callback within 72 hours of discharge had a 9.1% readmission rate; those who did not had 21.3%.
- No statistically significant change in case-mix index, length of stay, or admission diagnosis distribution.

**Risk if no action taken:** $1.8M penalty exposure, plus quality measure degradation that puts the system at risk of dropping below 4 stars on the CMS Hospital Compare program.

## Recommendation
1. **Restore the pharmacist callback workflow** in Epic by January 5, 2026. Owner: Director of Pharmacy + IT Applications. Estimated effort: 2 sprints.
2. **Reinstate the 30-minute inpatient pharmacy consult** for CHF patients pending the staffing analysis below.
3. **Pilot a 7-day post-discharge nurse home visit program** for high-risk CHF/COPD patients, modeled on the 2022 program. Owner: VP of Care Management. Funded via Q1 budget reallocation.
4. **Hire 2 additional clinical pharmacists** to permanently restore capacity. Compensation cost: $340K annually. Expected ROI: avoided penalties + reduced readmission costs = $2.4M annually based on 2022 pilot data.

**Decision requested from ELT:** Approve hiring authorization (item 4) and budget reallocation for nurse home visit pilot (item 3) at the December 8 ELT meeting.
"""

with open(f"{SBAR_PATH}/sbar_2025_q4_06_readmission_variance.md", "w") as f:
    f.write(SBAR_README)
print("Wrote: sbar_2025_q4_06_readmission_variance.md")

# COMMAND ----------

SBAR_ED = """# ED Throughput Improvement Initiative — Status Update

**Author:** Nina Patel, VP of Operations
**Date:** November 17, 2025
**Audience:** Executive Leadership Team

## Situation
ED door-to-disposition time has increased from a Q2 baseline of 4.1 hours to **5.7 hours** in October — a 39% degradation. Patient satisfaction (Press Ganey ED domain) has dropped 18 percentile points. Left-without-being-seen (LWBS) rate is at 4.9%, double our 2.5% target.

## Background
Three factors driving the trend:

1. **ED volume up 14%** vs. prior year, driven by population growth in the western service area and the closure of a competitor's ED in August.
2. **Two ED physicians on extended leave** (one parental, one medical) since September, reducing physician coverage by 22%.
3. **Radiology turnaround** for ED CT studies has slipped from a 38-minute median to 71 minutes due to a backfill gap on the evening shift.

## Assessment
Volume increase alone explains roughly 30% of the throughput degradation. The remaining 70% is attributable to staffing gaps in radiology and ED physician coverage. The radiology bottleneck is the highest-leverage intervention point — it sits in the critical path for ~60% of ED visits.

## Recommendation
1. Add a dedicated **evening-shift radiologist** (3pm-11pm) via locum tenens through end of Q1 2026. Cost: $180K through March.
2. Approve the **fast-track triage protocol revision** drafted by the ED medical director. Estimated to redirect 12-15% of low-acuity visits to a 90-minute parallel track.
3. Backfill the two ED physician leaves with locum coverage immediately.

**Status:** Recommendations 1 and 3 approved at November 10 ELT. Recommendation 2 pending Quality Committee review on November 24.
"""

with open(f"{SBAR_PATH}/sbar_2025_q4_05_ed_throughput.md", "w") as f:
    f.write(SBAR_ED)
print("Wrote: sbar_2025_q4_05_ed_throughput.md")

# COMMAND ----------

SBAR_CONTRACT = """# Anthem Payer Contract Renegotiation — Status Update

**Author:** Nina Patel, VP of Operations (on behalf of CFO)
**Date:** November 4, 2025
**Audience:** Executive Leadership Team

## Situation
The current Anthem commercial contract expires **December 31, 2025**. Anthem's opening offer is a **4.2% rate increase** over the 3-year term. Our requested rate increase is **7.8%**, justified by case-mix shift, inflation, and the wage index correction. Gap at proposed rates: **-$3.2M annual revenue** vs. our planned scenario.

## Background
- 2023-2025 contract was a 3-year deal at 3.1% annual escalator.
- 2024 patient mix shifted toward higher-acuity inpatient and observation cases (case-mix index up 6.4%).
- Volume up 11% over the contract term.
- Comparable peer hospital systems in the region settled at 6.0%-7.2% rate increases in 2025 negotiations (per HFMA benchmarks).

## Assessment
Anthem's 4.2% offer underweights the volume and acuity contribution and effectively gives them a real-terms rate cut after inflation. We have leverage: Anthem represents 28% of our commercial volume, but we represent the largest in-network provider for their book of business in the western service area.

Negotiation team recommends a **6.5% counter** with a 3-year term, contingent on a value-based contract addendum tied to readmission and length-of-stay performance.

## Recommendation
Authorize the negotiating team to:
1. Counter at **6.5%** with 3-year term.
2. Add a **value-based contract addendum** with shared-savings on readmissions, capped at 1.5% upside/downside.
3. Establish a walk-away threshold at **5.5%** — below this, recommend transition planning for an out-of-network scenario through Q2 2026.

**Decision requested from ELT:** Approve counter-offer parameters at the November 10 ELT meeting.
"""

with open(f"{SBAR_PATH}/sbar_2025_q4_04_anthem_contract.md", "w") as f:
    f.write(SBAR_CONTRACT)
print("Wrote: sbar_2025_q4_04_anthem_contract.md")

# COMMAND ----------

SBAR_QUALITY = """# CMS Star Quality Measure Performance — Mid-Cycle Review

**Author:** Nina Patel, VP of Operations
**Date:** October 21, 2025
**Audience:** Executive Leadership Team

## Situation
Mid-cycle CMS Star Ratings analysis shows **4 of 12 measures** below the 4-star threshold, putting our overall rating at risk of dropping from 4 stars to 3 stars in the 2026 release. Affected measures: Diabetes Care (HbA1c control), BP Control, Breast Cancer Screening (BCS), and Care Coordination (post-discharge follow-up).

## Background
- 2024 release: 4 stars overall (10 of 12 measures at 4-star or above).
- HEDIS data trends suggest the slip began in Q2 2025 and accelerated in Q3.
- Diabetes Care and BP Control are tied to the same underlying issue: the rooming workflow change implemented in February 2025 reduced standing-order completion rates.
- BCS slip correlates with the loss of 2 mammography techs (one resigned, one extended leave).
- Care Coordination ties back to the same pharmacist workflow issue identified in the readmission SBAR.

## Assessment
Three of the four measures are recoverable in the current cycle if interventions land before December 31. BCS is unlikely to recover this cycle given the lead time on hiring and the screening backlog.

## Recommendation
1. **Diabetes/BP Control:** Restore the rooming workflow to pre-February state. Owner: VP of Ambulatory Operations. Target: November 30.
2. **Care Coordination:** Tied to the readmission SBAR recommendations (pharmacist callback restore + nurse home visit pilot). Already in flight.
3. **BCS:** Accept partial-cycle recovery; submit recovery plan to CMS as part of the QAPI submission. Hire 2 mammography techs for 2026 cycle.
4. **Stand up an automated quality measure pipeline** to replace manual chart review. Reduces measurement lag from quarterly to monthly. Cost: $480K (one-time).

**Decision requested from ELT:** Approve quality measure pipeline investment (item 4) at the October 27 ELT meeting.
"""

with open(f"{SBAR_PATH}/sbar_2025_q4_03_cms_star_measures.md", "w") as f:
    f.write(SBAR_QUALITY)
print("Wrote: sbar_2025_q4_03_cms_star_measures.md")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Supplemental documents
# MAGIC
# MAGIC The Knowledge Assistant will ground on these. Two key shapes:
# MAGIC 1. **Numeric/operational reference data** (KPI exports, contract terms, staffing reports)
# MAGIC 2. **Narrative context** (board minutes, prior SBARs, policy documents, prior pilot results)
# MAGIC
# MAGIC The 2023 Joint Commission Site Visit Report is intentionally **omitted** here.
# MAGIC The demo storyline shows the dashboard flagging an unanswered question about it,
# MAGIC and notebook `04_close_the_gap.py` uploads the missing PDF to demonstrate the
# MAGIC closed-loop refresh.

# COMMAND ----------

SUPP_DOCS = {
    "kpi_dashboard_export_q3_2025.md": """# Q3 2025 Operational KPI Dashboard Export

Generated: October 1, 2025

## Inpatient Operations
| Metric | Q3 Actual | Q3 Target | YoY Change |
|---|---|---|---|
| 30-day all-cause readmission rate | 14.8% | 14.5% | +0.4pp |
| 30-day CHF readmission rate | 18.6% | 18.0% | +1.2pp |
| 30-day COPD readmission rate | 17.2% | 17.0% | +0.5pp |
| Average length of stay (ALOS) | 4.6 days | 4.5 days | -0.1 days |
| Case-mix index (CMI) | 1.78 | 1.74 | +6.4% |
| Hospital-acquired conditions (HACs) | 12 | 14 | -1 |

## ED Operations
| Metric | Q3 Actual | Q3 Target | YoY Change |
|---|---|---|---|
| Door-to-disposition time | 4.7 hrs | 4.0 hrs | +14% |
| LWBS rate | 3.6% | 2.5% | +1.4pp |
| ED volume | 28,400 | 25,000 | +14% |
| Door-to-doc | 26 min | 20 min | +6 min |

## Pharmacy
| Metric | Q3 Actual | Q3 Target | YoY Change |
|---|---|---|---|
| Pharmacist post-discharge callback completion | 47% | 85% | -40pp |
| Inpatient pharmacy consult completion | 91% | 95% | -3pp |
| Medication reconciliation accuracy | 96% | 97% | -1pp |

## Quality (HEDIS-aligned)
| Measure | Q3 Score | Threshold for 4-star | Status |
|---|---|---|---|
| HbA1c control (<8%) | 64% | 67% | Below |
| BP control (<140/90) | 71% | 74% | Below |
| Breast cancer screening | 68% | 72% | Below |
| Care coordination (post-DC follow-up) | 78% | 82% | Below |
| Tobacco cessation counseling | 84% | 80% | Above |
""",

    "ehr_upgrade_project_charter_2025.md": """# EHR Upgrade Project Charter — Epic 2025.1

**Approved:** July 15, 2025
**Go-Live:** October 4, 2025
**Project Sponsor:** CIO

## Scope
Upgrade Epic from version 2024.2 to 2025.1 across all inpatient, ambulatory, and ED workflows. Includes:
- Updated discharge planning module
- Revised medication reconciliation workflow
- New patient communication preferences UI
- Deprecation of legacy custom callback module (replaced by built-in Epic communication center)

## Known Risks
- Legacy custom workflows may not migrate cleanly. The pharmacist post-discharge callback workflow built in 2021 is **flagged for re-mapping** in the upgrade workbook (Risk Register Item #14).
- Standing order behavior in the rooming workflow has changed; nursing leadership must validate.

## Success Criteria
- Zero unplanned downtime > 30 minutes
- 95% user satisfaction at 30-day post-go-live survey
- All custom workflows mapped or formally retired

## Notes (Post Go-Live)
- October 12: Risk Register Item #14 marked "DEFERRED" — pharmacist callback workflow re-mapping deprioritized due to compressed go-live timeline. Owner: pharmacy informaticist.
""",

    "chf_discharge_protocol_v3_2.md": """# CHF Discharge Protocol v3.2

**Effective Date:** October 1, 2025
**Supersedes:** v3.1 (effective March 2024)

## Summary of Changes
1. **Inpatient pharmacy consult duration** reduced from 30 minutes to 15 minutes for patients classified as "stable CHF" at discharge readiness.
2. **Patient education materials** updated to align with American Heart Association 2025 guidelines.
3. **Diuretic dose timing** at discharge revised based on KAREN trial findings.

## Rationale for Pharmacy Consult Reduction
Clinical pharmacy capacity constraints during the recruitment lag for the open inpatient pharmacist FTEs (2 vacancies as of August 2025). Stable CHF cohort represents ~62% of CHF discharges and is judged lower-risk for medication-related readmission events.

## Stable CHF Criteria (must meet all)
- NYHA Class I-II at discharge
- No diuretic dose change in past 48 hours
- LVEF documented within past 12 months
- No active infection or AKI

## Approval
- VP Quality
- Chief Medical Officer
- Director of Pharmacy
""",

    "pharmacy_callback_pilot_results_2022.md": """# Pharmacy Post-Discharge Callback Program — Pilot Results

**Pilot Period:** January 2022 – June 2022
**Author:** Director of Pharmacy
**Date Issued:** August 2022

## Executive Summary
Six-month pilot of a structured pharmacist post-discharge callback program for CHF and COPD patients showed a **3.1 percentage-point reduction** in 30-day CHF readmission rate and a **2.4 percentage-point reduction** for COPD. Net financial impact: $1.6M in avoided readmission costs and CMS penalties.

## Methodology
- Target population: All CHF and COPD discharges with at least one prescription medication change
- Intervention: Structured pharmacist phone callback within 72 hours of discharge
- Callback content: Medication reconciliation, side effect screening, refill confirmation, red-flag symptom check
- Comparison: Pre-pilot baseline period (July-December 2021)

## Results
| Cohort | Pre-Pilot Rate | Pilot Rate | Change |
|---|---|---|---|
| CHF 30-day readmission | 19.8% | 16.7% | -3.1pp |
| COPD 30-day readmission | 18.1% | 15.7% | -2.4pp |
| All-cause readmission | 14.5% | 13.2% | -1.3pp |

## Key Success Factors
- Standardized callback script with branching logic
- Direct integration with EHR for medication list and discharge instructions
- Pharmacist coverage 7 days/week
- 87% callback completion rate (defined as patient reached and full script completed)

## Discontinuation
Program was discontinued in Q3 2023 as part of the pharmacy department staffing reorganization. The supporting Epic workflow remained in place but utilization declined to ~40% of discharges by mid-2024.

## Recommendation for Reinstatement
If reinstated with 2 additional FTE clinical pharmacists, the program is projected to deliver $2.4M in annual avoided cost based on 2025 readmission rates and current case volume.
""",

    "joint_commission_site_visit_2022.md": """# Joint Commission Site Visit Report — June 2022

**Survey Type:** Triennial Accreditation Survey
**Survey Dates:** June 13-17, 2022
**Outcome:** Accreditation renewed with 4 Requirements for Improvement (RFIs)

## Findings Summary
**Strengths Noted:**
- Patient safety culture survey results
- Falls reduction program
- Hand hygiene compliance

**Requirements for Improvement:**
1. **MM.04.01.01** - Medication storage in 2 inpatient units found unlocked
2. **PC.02.02.01** - Two charts reviewed had incomplete pain reassessment documentation
3. **NPSG.06.01.01** - Alarm management policy not consistently followed in ICU
4. **EC.02.06.01** - Two stairwell doors found propped open during survey

**Discharge Process Observations:**
The survey team observed the **structured pharmacist post-discharge callback program** during inpatient unit rounds. The program was cited as an exemplary practice in the survey closeout meeting and noted in the surveyor exit summary as a contributor to safe transitions of care.

## Plan of Correction
All four RFIs were addressed within the 60-day evidence-of-standards-compliance window. ESC submitted September 2022 and accepted October 2022.

## Next Survey
Triennial survey scheduled for 2025 (estimated June-September 2025 window).
""",

    "anthem_contract_2023_2025_terms.md": """# Anthem Commercial Contract — 2023-2025 Terms Summary

**Effective:** January 1, 2023
**Expiration:** December 31, 2025
**Contract Type:** PPO + HMO commercial network

## Rate Structure
- Year 1 (2023): Base rate
- Year 2 (2024): 3.1% escalator
- Year 3 (2025): 3.1% escalator (compounded)

## Volume and Mix at Contract Signing (2022 Baseline)
- Inpatient discharges: 8,400/year
- Outpatient visits: 142,000/year
- ED visits: 24,000/year
- Case-mix index: 1.67

## Volume and Mix at Contract End (2025 Estimated)
- Inpatient discharges: 9,300/year (+11%)
- Outpatient visits: 158,000/year (+11%)
- ED visits: 28,400/year (+18%)
- Case-mix index: 1.78 (+6.4%)

## Key Provisions
- 90-day termination notice required
- Out-of-network rates apply if no contract renewal by 12/31/2025
- Value-based contract addendum optional (currently not in effect)
- Audit rights for medical necessity documentation

## Walk-Away Analysis
At a 4.2% offer (Anthem opening), revenue gap vs. 7.8% requested = ~$3.2M annually. At a 5.5% rate, gap narrows to ~$1.4M annually. Out-of-network scenario projects -$11M annual loss in the first year due to patient leakage and bad debt.
""",

    "payer_mix_q1_q3_2025.md": """# Payer Mix Analysis — Q1-Q3 2025

| Payer | Volume Share | Revenue Share | YoY Volume Δ |
|---|---|---|---|
| Medicare FFS | 38% | 32% | +2% |
| Medicare Advantage | 14% | 13% | +18% |
| Medicaid | 11% | 7% | +4% |
| Anthem (commercial) | 28% | 31% | +11% |
| BCBS (commercial) | 5% | 6% | +3% |
| Aetna | 2% | 3% | -1% |
| Self-pay/Other | 2% | 8% | +1% |

## Notes
- Anthem volume growth driven by competitor ED closure in August (estimated +400 visits/quarter going forward).
- Medicare Advantage growth is the highest-leverage trend — these contracts are individually negotiated and offer value-based contract opportunities.
- Self-pay/other revenue share is overweighted vs. volume due to charity care policy and bad debt write-offs.
""",

    "cms_star_ratings_history.md": """# CMS Star Ratings History

| Cycle | Overall | Patient Experience | Process | Outcomes | Safety |
|---|---|---|---|---|---|
| 2021 | 3 stars | 3 | 4 | 3 | 3 |
| 2022 | 4 stars | 4 | 4 | 4 | 4 |
| 2023 | 4 stars | 4 | 4 | 4 | 4 |
| 2024 | 4 stars | 4 | 4 | 4 | 4 |
| 2025 (current) | 4 stars | 4 | 4 | 4 | 3 |
| 2026 (projected) | **3 stars** | 4 | 3 | 3 | 3 |

## At-Risk Measures for 2026 Cycle
1. HbA1c control < 8% (Diabetes Care)
2. BP control < 140/90 (Hypertension)
3. Breast Cancer Screening
4. Care Coordination (post-discharge follow-up)

## Star Rating Financial Impact
- Each star step is worth approximately $4-6M in annual reimbursement adjustments under value-based purchasing programs.
- A drop to 3 stars also affects market positioning vs. competitor systems and patient choice in Medicare Advantage open enrollment.
""",

    "hedis_measure_performance_q3_2025.md": """# HEDIS Measure Performance — Q3 2025 Mid-Cycle

| Measure | Q1 | Q2 | Q3 | 4-star Threshold |
|---|---|---|---|---|
| HbA1c < 8% | 68% | 65% | 64% | 67% |
| BP control | 75% | 73% | 71% | 74% |
| BCS | 70% | 69% | 68% | 72% |
| Care coordination | 81% | 79% | 78% | 82% |
| Tobacco cessation | 86% | 85% | 84% | 80% |
| Statin therapy (CV) | 82% | 82% | 81% | 78% |
| Colorectal cancer screening | 74% | 74% | 75% | 73% |
| Childhood immunization | 91% | 90% | 90% | 88% |

## Trend Analysis
- HbA1c and BP control trends started in Q2 2025, coinciding with the rooming workflow change.
- BCS trend is staffing-driven (2 tech vacancies).
- Care coordination ties to the pharmacist post-discharge callback issue.

## Recovery Probability for 2026 Cycle
- HbA1c: High (rooming workflow restore is straightforward)
- BP: High (same)
- Care coordination: High (tied to readmission SBAR recommendations)
- BCS: Low (hiring lead time exceeds remaining cycle)
""",

    "board_meeting_minutes_q3_review.md": """# Board of Directors Meeting Minutes — Q3 Review

**Date:** October 8, 2025
**Attendees:** Board chair, 8 board members, CEO, CFO, COO, CMO, VP of Operations (Nina Patel)

## Q3 Operational Review
The board reviewed Q3 KPIs presented by VP of Operations. Discussion centered on:

1. **Readmission rate trend** — board chair expressed concern about the 0.4pp slip and asked for a deeper analysis at the November briefing. *Action item assigned to Nina Patel.*
2. **ED throughput degradation** — board approved authorization for evening-shift radiologist locum coverage and ED physician backfill, expedited.
3. **Anthem contract negotiations** — finance committee authorized to develop counter-offer parameters for ELT review by November 10.
4. **CMS Star Ratings** — board requested the quality team prepare a recovery plan for the 2026 cycle.

## Strategic Discussion Items
- Population health investment (deferred to Q4)
- Capital plan for radiology expansion (deferred to Q4)
- Service line review (in progress)

## Next Meeting
December 8, 2025
""",

    "quality_strategic_plan_2025.md": """# Quality Improvement Strategic Plan — 2025

## Vision
Achieve and sustain 5-star CMS Hospital Compare rating by end of 2027.

## 2025 Objectives
1. Maintain 4-star rating in 2025 cycle (achieved)
2. Reduce 30-day all-cause readmission rate to 14.0% by Q4 (currently at risk)
3. Improve HEDIS performance on diabetes care, BP control, and care coordination
4. Stand up automated quality measure pipeline by Q1 2026

## Resource Allocation
- 12 FTE quality team members
- Quality measure pipeline build: $480K capital + $120K annual operating
- HEDIS abstraction tools: $80K annual

## Risks
- Manual chart review limits measurement frequency to quarterly
- Staffing turnover in quality team (~22% annual turnover)
- HEDIS measure specifications change annually, requiring re-tooling

## Success Metrics
- Star rating maintenance/improvement
- HEDIS measure performance vs. CMS thresholds
- Pipeline implementation milestones
""",

    "ed_volume_trends_2024_2025.md": """# ED Volume Trends — 2024 to 2025

## Monthly Volume
| Month | 2024 | 2025 | Change |
|---|---|---|---|
| January | 2,100 | 2,250 | +7% |
| February | 1,950 | 2,180 | +12% |
| March | 2,200 | 2,420 | +10% |
| April | 2,150 | 2,380 | +11% |
| May | 2,300 | 2,510 | +9% |
| June | 2,400 | 2,610 | +9% |
| July | 2,450 | 2,680 | +9% |
| August | 2,500 | 2,950 | +18% |
| September | 2,400 | 2,820 | +18% |
| October | 2,350 | 2,810 | +20% |

## Drivers
- Population growth in western service area: ~3% annually
- Competitor ED closure in August 2025 (Westmont Regional Hospital ED): estimated +400 visits/month
- Seasonal flu and RSV activity has been within normal ranges

## Acuity Mix
| ESI Level | 2024 Share | 2025 Share | Change |
|---|---|---|---|
| ESI-1 (resuscitation) | 1.2% | 1.3% | +0.1pp |
| ESI-2 (emergent) | 12% | 14% | +2pp |
| ESI-3 (urgent) | 48% | 50% | +2pp |
| ESI-4 (less urgent) | 28% | 25% | -3pp |
| ESI-5 (non-urgent) | 11% | 10% | -1pp |

Higher acuity mix is consistent with the volume growth being driven by displaced patients from the closed competitor ED rather than primary-care-substitutable visits.
""",

    "radiology_turnaround_analysis.md": """# Radiology Turnaround Time Analysis

**Period:** Q3 2025
**Author:** Director of Imaging

## ED CT Turnaround
| Metric | Q2 2025 | Q3 2025 | Change |
|---|---|---|---|
| Median time from order to read | 38 min | 71 min | +87% |
| 90th percentile | 62 min | 118 min | +90% |
| Median time from order to scan | 19 min | 22 min | +16% |
| Median time from scan to read | 19 min | 49 min | +158% |

The bottleneck is in the **scan-to-read** phase, not the **order-to-scan** phase. Translation: patients are getting scanned promptly, but reads are queuing.

## Root Cause
Evening-shift radiologist FTE went on extended leave in early September. The remaining day-shift radiologist is covering reads during peak ED volume hours (3pm-11pm) on top of the standard daytime workload.

## Mitigation Options
1. **Locum tenens evening radiologist** — $180K through Q1 2026, 8-week start time. Recommended.
2. **Outsourced teleradiology for evening shift** — $120K through Q1, 2-week start time. Faster but lower quality (per quality team review).
3. **Internal redistribution** — extends day-shift hours, would lead to burnout and turnover risk. Not recommended.

## Recommendation
Pursue option 1 (locum) with option 2 (teleradiology) as bridge coverage during the 8-week start window.
""",

    "prior_sbar_q1_readmission_initiative.md": """# Q1 2025 SBAR — Readmission Reduction Initiative Launch

**Author:** Nina Patel, VP of Operations
**Date:** January 28, 2025
**Audience:** Executive Leadership Team

## Situation
2024 closed with a 30-day all-cause readmission rate of 14.7%, slightly above our 14.5% target. Initiating a structured 2025 readmission reduction initiative to drive the rate to 14.0% by year-end.

## Background
- 2023: 15.2%
- 2024: 14.7%
- 2025 target: 14.0%

The Q1 2022 pharmacy callback pilot (referenced in supplemental materials) demonstrated a meaningful reduction in CHF/COPD readmissions but was discontinued in 2023 due to staffing changes.

## Assessment
Three intervention areas with strong evidence base:
1. Pharmacist post-discharge callback (proven, previously piloted)
2. Nurse-led 7-day post-discharge home visits (industry best practice)
3. Care management partnership for high-risk patients (currently underutilized)

## Recommendation
Launch a Q1-Q2 design phase to scope these interventions for funding consideration in the Q3 budget cycle. Final implementation decisions deferred to Q3.

## Outcome
Q3 budget cycle deprioritized this initiative in favor of EHR upgrade timeline. Decision deferred to 2026 planning cycle.
""",

    "nursing_staffing_plan_q4.md": """# Nursing Staffing Plan — Q4 2025

## Overall Position
- Authorized FTE: 612 nursing FTEs across all units
- Actual FTE: 587 (96% filled)
- Open requisitions: 25

## Critical Vacancies
- **Emergency Department:** 4 RN vacancies (16-20% gap depending on shift)
- **Med-Surg Tower 4:** 6 RN vacancies (12% gap)
- **ICU:** 2 RN vacancies (4% gap, manageable)
- **Care Management:** 3 RN vacancies (these are the 7-day post-discharge home visit roles needed for the readmission reduction recommendation)

## Travel Nurse Coverage
- 24 travel nurses currently filling gaps
- Cost premium: ~$2.4M annualized vs. permanent FTE cost
- Plan: ramp down to 12 travelers by Q2 2026 as permanent hires onboard

## Risk
- Care Management vacancies are blocking the nurse home visit pilot recommendation in the readmission SBAR.
- Without those 3 FTE filled, the program cannot launch as designed.
""",

    "pharmacist_productivity_report.md": """# Clinical Pharmacist Productivity Report — Q3 2025

**Author:** Director of Pharmacy

## FTE Status
- Authorized: 18 clinical pharmacist FTE (across inpatient, ED, and ambulatory)
- Filled: 16 (89%)
- Open: 2 (both inpatient)

## Activity Metrics
| Activity | Target/Day | Actual/Day | Notes |
|---|---|---|---|
| Inpatient consults | 32 | 28 | Below target due to vacancies |
| Discharge medication reconciliations | 65 | 58 | |
| Post-discharge callbacks | 24 | 11 | Significantly below target — workflow issue post-EHR upgrade |
| Antimicrobial stewardship rounds | 4 | 4 | On target |

## Workflow Issue (Post-EHR Upgrade, October 2025)
The post-discharge callback workflow that was active prior to the Epic 2025.1 upgrade has not been re-mapped. Pharmacists are using the new Epic communication center but it lacks:
- The branching script logic
- Direct integration with the medication reconciliation note
- Auto-assignment of callback tasks based on discharge cohort

Workaround: pharmacists manually identify callback candidates from the discharge list, but this is incomplete and inconsistent. Callback completion has dropped to ~47% from a pre-upgrade level of ~87%.

## Recommendation
Tier 1 priority: re-map the callback workflow in Epic. Estimated 2 sprints with current pharmacy informaticist support.
Tier 2 priority: hire 2 inpatient clinical pharmacist FTE to restore capacity.
""",

    "patient_satisfaction_press_ganey_q3.md": """# Press Ganey Patient Satisfaction — Q3 2025

## Overall HCAHPS Top-Box Performance
| Domain | Q2 2025 | Q3 2025 | National Percentile |
|---|---|---|---|
| Overall hospital rating (9-10) | 71% | 69% | 58th |
| Communication with nurses | 78% | 77% | 65th |
| Communication with doctors | 79% | 79% | 71st |
| Responsiveness of staff | 64% | 61% | 51st |
| Communication about medicines | 64% | 60% | 48th |
| Discharge information | 86% | 84% | 70th |
| Care transition | 51% | 49% | 38th |

## Notable Trends
- **Communication about medicines** dropped 4pp — correlates with the pharmacist callback program issues post-EHR upgrade.
- **Care transition** remains a chronic underperformer — significantly below national median.
- **ED domain (separate report)** dropped 18 percentile points; tied to throughput issues.

## Action Plan
- Pharmacy callback program restoration (referenced in readmission SBAR) is expected to lift "communication about medicines" and "care transition" domains.
- Service excellence training for top-of-license inpatient nursing rolling out in Q1 2026.
""",

    "ka_glossary.md": """# Glossary — Healthcare Operations Terms

This document is included in the supplemental docs corpus to help the Knowledge Assistant interpret domain abbreviations and terminology.

| Term | Definition |
|---|---|
| SBAR | Situation, Background, Assessment, Recommendation - structured communication framework |
| CHF | Congestive Heart Failure |
| COPD | Chronic Obstructive Pulmonary Disease |
| CMI | Case-Mix Index - severity-adjusted measure of patient complexity |
| CMS | Centers for Medicare & Medicaid Services |
| HEDIS | Healthcare Effectiveness Data and Information Set |
| HCAHPS | Hospital Consumer Assessment of Healthcare Providers and Systems |
| LWBS | Left Without Being Seen (ED metric) |
| ESI | Emergency Severity Index (1-5 acuity scale) |
| RFI | Requirement for Improvement (Joint Commission finding) |
| ESC | Evidence of Standards Compliance |
| QAPI | Quality Assessment and Performance Improvement |
| HbA1c | Glycated hemoglobin (diabetes control measure) |
| LVEF | Left Ventricular Ejection Fraction |
| NYHA | New York Heart Association (heart failure classification) |
| BCS | Breast Cancer Screening |
| AKI | Acute Kidney Injury |
| FTE | Full-Time Equivalent |
| ELT | Executive Leadership Team |
| ED | Emergency Department |
""",
}

for filename, content in SUPP_DOCS.items():
    with open(f"{SUPP_PATH}/{filename}", "w") as f:
        f.write(content)
    print(f"Wrote: {filename}")

print(f"\nTotal supplemental docs: {len(SUPP_DOCS)}")
print("Note: joint_commission_site_visit_2023.md is INTENTIONALLY EXCLUDED — used in 04_close_the_gap.py")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Verify

# COMMAND ----------

import os
print(f"SBAR documents in {SBAR_PATH}:")
for f in sorted(os.listdir(SBAR_PATH)):
    print(f"  {f}")

print(f"\nSupplemental docs in {SUPP_PATH}:")
for f in sorted(os.listdir(SUPP_PATH)):
    print(f"  {f}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Next steps
# MAGIC
# MAGIC - Notebook 02: provision Lakebase + audit_events table, seed 6-executive interaction history
# MAGIC - Notebook 03: set up the Knowledge Assistant grounded on the supplemental_docs volume
# MAGIC - Notebook 04: the "close the gap" demo step that adds the 2023 Joint Commission report
