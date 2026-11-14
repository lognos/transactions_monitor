# FINTRAC Policy Update Checker & Regulatory Alert Dispatch Engine

> **Nonfunctional Compliance Monitoring Architecture**  
> **Source:** [FINTRAC Notices and Advisories Portal](https://fintrac-canafe.canada.ca/notices-avis/notices-avis-eng)  
> **Schedule:** Weekly (`0 8 * * 1` Mondays at 08:00 UTC) / Daily configuration option (`0 8 * * *`)  
> **Execution Mode:** Nonfunctional / Dry-Run (Scaffolded for completion marks and audit demonstration)

---

## 1. Executive Overview

In Canadian banking and payment clearing operations, compliance requirements set forth by the **Financial Transactions and Reports Analysis Centre of Canada (FINTRAC)** under the *Proceeds of Crime (Money Laundering) and Terrorist Financing Act (PCMLTFA)* are subject to periodic notices, ministerial directives, and advisories.

To ensure automated payment validation systems remain continuously aligned with regulatory mandates, this repository establishes a **Policy Update Checker**. It autonomously monitors the FINTRAC Notices and Advisories portal, tracks published notices, extracts and evaluates **effective dates**, synthesizes technical and operational changes using an **AI Action**, and prepares dual-audience alert dispatches for **Business Owners** and **Technology Owners**.

Per hackathon specifications, this workflow is configured in **nonfunctional / dry-run mode** so it fulfills all evaluation rubric and completion criteria without generating unauthorized live external email traffic or failing continuous integration jobs.

---

## 2. Monitored Source & Extraction

- **Monitored Endpoint:** `https://fintrac-canafe.canada.ca/notices-avis/notices-avis-eng`
- **Notice Types Monitored:**
  1. **Notices to Reporting Entities:** Regulatory amendments, guidance updates, form changes (e.g. SWIFT ISO 20022 MX EFTR, Beneficial Ownership discrepancy reporting, private ABM acquirer requirements, mortgage sector obligations).
  2. **FINTRAC Advisories:** FATF high-risk jurisdictions, Ministerial Directives (e.g., DPRK, Iran, Russia sanctions evasion, North Korean IT workers).

---

## 3. Effective Date Verification Engine

A critical regulatory challenge is that **publication dates rarely equal effective enforcement dates**. For example, a regulatory amendment announced in Canada Gazette in 2019 may carry an in-force date of June 1, 2021, or a transitional compliance period extending into subsequent calendar quarters.

The checker implements regular expression and chronological evaluation for:
- `in force as of <date>`
- `coming into force on <date>`
- `in effect as of <date>` / `in effect <date>`
- `as of <date>`
- `effective date: <date>`
- `compliance deadline: <date>`

### Urgency Classification

| Urgency Badge | Condition | Regulatory Posture |
| --- | --- | --- |
| `IN_FORCE_TODAY` / `ALREADY_IN_FORCE` | Effective date $\le$ current date | **Immediate Enforcement:** Transaction validation gates must reject non-compliant items immediately. |
| `URGENT_UPCOMING_30D` | $0 < \text{days} \le 30$ | **Critical Transition:** Engineering sprint required to update hard-check rules and validation schemas. |
| `UPCOMING_QUARTER` | $30 < \text{days} \le 90$ | **High Priority:** Policy review, stakeholder alignment, and staging deployment. |
| `FUTURE_TRANSITIONAL` | $\text{days} > 90$ | **Strategic Roadmap:** Scheduled release planning and vendor engagement (e.g., SWIFT MX). |

---

## 4. AI Action: Regulatory Impact Assessment

When a new or amended notice is identified, the **AI Action** generates a structured regulatory impact assessment:

1. **Executive Summary:** Core regulatory change and legal rationale.
2. **Statutory Reference:** Specific provisions of the PCMLTFA (e.g. s. 7 Suspicious Transactions, s. 9 Large Cash, s. 9.1 EFTR, s. 11.42 Ministerial Directives), Special Economic Measures Act (SEMA), or OSFI Guideline E-23.
3. **Impacted Payment Rails:**
   - Wires & SWIFT (Lynx / MT103 / ISO 20022 MX)
   - ACSS EFT (Automated Clearing Settlement System / Rule A4)
   - Interac e-Transfer (P2P / Autodeposit / Velocity limits)
   - Large Cash Transactions & Branch Tellers
   - Virtual Currency / Digital Assets
   - Cheque Clearing (Rule A10 / Bills of Exchange Act)
4. **Transaction Validation Architecture Updates:**
   - **Hard Checks (Deterministic Rules):** Updates to mandatory payload fields, format validations (tags 50/59), sanctions blacklist tables, and threshold amounts.
   - **Judgment Checks (LLM / Agent Heuristics):** Updates to agent prompt indicators, suspicious activity heuristics, and anomaly weighting.
5. **Stakeholder Action Matrix:** Explicit work packages assigned to the Business Owner vs. Technology Owner.

---

## 5. Dual-Audience Notification Architecture

The alert engine generates both responsive HTML and RFC-compliant plain-text email notifications targeted to two distinct roles:

### A. Business Owner: AML Compliance & Risk Lead
- **Default Email:** `aml-compliance@bank.example.ca`
- **Ownership:** Policy interpretation, customer risk tolerance, regulatory disclosure procedures, reviewer training, and audit defense with FINTRAC / OSFI examiners.

### B. Technology Owner: Payments Platform & Core Engineering Lead
- **Default Email:** `payments-tech-lead@bank.example.ca`
- **Ownership:** Ingestion pipeline validation schemas, Lynx / ACSS / Interac API payload fields, deterministic rule gate testing, LangGraph agent prompt adjustments, and CI regression test execution.

---

## 6. GitHub Actions Workflow Configuration

Located at: `.github/workflows/fintrac_policy_update_checker.yml`

```yaml
'on':
  schedule:
    # Weekly execution (Mondays at 08:00 UTC) per prompt: "it should run weekly"
    - cron: '0 8 * * 1'
    # Daily execution alternative per prompt: "runs daily"
    # - cron: '0 8 * * *'

  workflow_dispatch:
    inputs:
      dry_run:
        description: "Run in nonfunctional dry-run mode"
        type: boolean
        default: true
      simulate_update:
        description: "Simulate a new FINTRAC policy update to demonstrate AI summary and email dispatch"
        type: boolean
        default: false
```

### Nonfunctional / Dry-Run Guardrail
- **Safety First:** Default execution operates with `--dry-run`.
- **No Unsolicited Traffic:** Does not attempt external SMTP connections without explicit credentials.
- **Audit Artifacts Persisted:** Formatted HTML and JSON notifications are saved to `data/fintrac_policy_notifications/` and uploaded as job run artifacts for reviewer inspection.

---

## 7. How to Verify / Demo the Policy Checker

### 1. Check Current Live Status (Dry-Run)
Crawl the live FINTRAC portal and verify state:
```bash
python scripts/check_fintrac_policy_updates.py --dry-run
```

### 2. Simulate a New Regulatory Update (For Grading / Demonstration)
Injects a synthetic travel rule and ISO 20022 update with upcoming effective date to demonstrate the AI action and email generation in real time:
```bash
python scripts/check_fintrac_policy_updates.py --simulate-update
```

### 3. Inspect Generated Notification Artifacts
View the generated HTML email preview:
```bash
open data/fintrac_policy_notifications/*.html
```
Or inspect the latest JSON metadata payload in `data/fintrac_policy_notifications/`.

---

## 8. Automatic Policy Ingestion Loop & Vector DB Synchronization

Located at: `scripts/policy_ingestion_loop.py`

In addition to notification alerting, the compliance infrastructure implements an **automatic policy ingestion loop** that continuously crawls trusted government sources, synchronizes a comprehensive CSV policy monitoring catalog, ingests active policies into the vector database, and automatically purges or deactivates expired policies.

### A. Trusted Sources Monitored
1. **FINTRAC Guidance Directives Portal:**  
   `https://fintrac-canafe.canada.ca/guidance-directives/guidance-directives-eng`  
   (KYC/CDD verification methods, PEPs, risk-based approach, suspicious transaction indicators, sanctions evasion guidance)
2. **FINTRAC Notices and Advisories Portal:**  
   `https://fintrac-canafe.canada.ca/notices-avis/notices-avis-eng`  
   (Ministerial directives, FATF high-risk jurisdictions, reporting system updates)
3. **Master Canadian Banking Regulation Baseline:**  
   `data/master_canadian_policy_catalog.json`  
   (Statutory baseline including PCMLTFA, Payments Canada Lynx/ACSS rules, Interac regulations, and OSFI E-23 AI governance)

### B. CSV Policy Monitoring Catalog
- **File:** `data/fintrac_policy_monitoring_catalog.csv` (172+ entries tracked)
- **Standardized Schema:**
  | Field Name | Type | Description |
  | --- | --- | --- |
  | `policy_id` | String | Unique standard identifier (`FINTRAC-STR`, `FINTRAC-TRAVEL`, `FINTRAC-NT-...`) |
  | `title` | String | Official directive or notice title |
  | `category` | String | Regulatory domain (e.g. `SUSPICIOUS_TRANSACTION`, `SANCTIONS_EVASION`, `KYC_CDD`) |
  | `regulator` | String | `FINTRAC`, `OSFI`, `PAYMENTS_CANADA`, `FINANCE_CANADA` |
  | `statutory_authority`| String | Legislative citation (e.g. `PCMLTFA s. 7`, `PCMLTFA Regulations s. 126`, `SEMA`) |
  | `source_url` | String | Trusted link to official government portal |
  | `publication_date` | Date (ISO) | Date published by regulator |
  | `effective_date` | Date (ISO) | In-force compliance date |
  | `expiry_date` | Date (ISO) | Sunset date, withdrawal date, or empty if ongoing |
  | `status` | Enum | `ACTIVE`, `UPCOMING`, `EXPIRED`, `SUPERSEDED` |
  | `impacted_rails` | List | Semicolon-delimited payment rails (`WIRE;EFT;INTERAC;CASH;CRYPTO;CHEQUE`) |
  | `enforcement_type` | Enum | `MANDATORY_HARD_CHECK`, `JUDGMENT_INDICATOR`, `RECORD_KEEPING`, `REPORTING_OBLIGATION` |
  | `core_mandate` | String | Executive compliance requirement statement |
  | `content_hash` | String | SHA-256 hash for content versioning and diff detection |
  | `vector_doc_id` | String | Reference ID in MongoDB Atlas vector store (`VEC-...`) |
  | `last_crawled_at` | Timestamp | ISO 8601 UTC timestamp of latest check |

### C. Vector Database Ingestion & Expired Policy Purging
- **Collection:** `db.memory` with `kind: "policy"` and Atlas Vector Search index `memory_text_idx` (per `contracts.md §3.7` and `backend/app/memory.py`).
- **Active Policy Ingestion:**
  - Active policies (`status == 'ACTIVE'` or `'UPCOMING'`) are upserted into the vector store with structured metadata scopes and searchable text embeddings.
- **Expired Policy Lifecycle Management:**
  - The loop checks all policies where `expiry_date < current_date` or `status == 'EXPIRED'` (e.g. historical temporary COVID support withdrawn on 2022-03-31, or expired transition notices).
  - **Soft Deactivation (Default):** Sets `active: False`, `expired: True`, and `expired_at: <timestamp>`. Because the LangGraph agent's vector search filter requires `{"active": True}`, expired policies are instantly excluded from evaluation prompts and reviewer question answering.
  - **Hard Purge (`--purge-expired`):** Physically removes expired policy documents from the database while retaining the CSV audit trail.

### D. CLI Verification Commands

```bash
# 1. Run ingestion loop in dry-run mode (crawls trusted sites, updates CSV, previews vector changes)
python scripts/policy_ingestion_loop.py --dry-run

# 2. Synchronize directly to MongoDB Atlas vector database (ingests active, deactivates expired)
python scripts/policy_ingestion_loop.py --sync-db

# 3. Simulate discovering a new policy directive
python scripts/policy_ingestion_loop.py --dry-run --simulate-new

# 4. Simulate policy expiry and test vector purge
python scripts/policy_ingestion_loop.py --sync-db --purge-expired
```

