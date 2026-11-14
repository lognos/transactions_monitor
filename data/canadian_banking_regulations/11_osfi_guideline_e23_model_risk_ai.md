# OSFI Guideline E-23: Enterprise Model Risk Management for AI in Canadian Banking

> **Payment Rail Scope:** `ALL_RAILS` (Wires, Cheques, Interac e-Transfer)  
> **Statutory / Regulatory Authority:** `OSFI Guideline E-23 (Takes effect May 1, 2027)`  
> **Official Source:** [https://www.osfi-bsif.gc.ca](https://www.osfi-bsif.gc.ca)  
> **Jurisdiction:** Canada (Office of the Superintendent of Financial Institutions - OSFI)  

---

## 1. Regulatory Mandate & Operational Summary
OSFI Guideline E-23 establishes prudential expectations for federally regulated financial institutions (FRFIs) deploying models, with an explicit modern scope encompassing Artificial Intelligence (AI) and Machine Learning (ML) decision engines. It mandates that financial institutions ensure AI agents are governed by human accountability, explainable decisions, and tamper-resistant auditability.

## 2. Deterministic Validation Thresholds & Prudential Principles
- **Rule ID:** `OSFI-E23-01`
- **Category:** `AI_MODEL_RISK_GOVERNANCE`
- **Payment Rail:** `ALL_RAILS`

### Core AI Governance Mandates:
1. **Identity & Human Accountability:**
   - Autonomous agents must never operate as unattached entities. Every action taken by an AI model must be legally attributed to a human operator or designated officer acting within authorized delegated limits.
2. **Pre-Execution Policy Interception (Maker-Checker):**
   - High-impact decisions (such as fund releases, credit alterations, and AML exceptions) must not be autonomously finalized by an LLM alone. A deterministic policy gate or four-eyes human review is required before state execution.
3. **Explainability & Decision Reconstructability:**
   - Every AI recommendation must generate an explainable audit trail detailing: the specific policy criteria evaluated, the evidence considered, precedent cases referenced, and the exact rationale.
4. **Tamper-Evident Audit Trail:**
   - Reviewers and OSFI compliance examiners must be able to reconstruct historical decisions without risk of retrospective record modification.
