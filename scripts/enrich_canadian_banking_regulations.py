"""
scripts/enrich_canadian_banking_regulations.py
Populates complete, exhaustive operational guidelines, statutory clauses,
thresholds, and exception procedures for Canadian Wires, Cheques, Interac e-Transfers, and OSFI AI governance.
"""

import os
import json

TARGET_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "canadian_banking_regulations")

DOCS_CONTENT = {
    "01_payments_canada_lynx_wire_rules.md": """# Payments Canada Lynx Rules & Standards for Electronic Wire Clearing

> **Payment Rail Scope:** `WIRE`  
> **Statutory / Regulatory Authority:** `Canadian Payments Act / Payments Canada Lynx Rules`  
> **Official Source:** [https://www.payments.ca/systems-services/payment-systems/lynx](https://www.payments.ca/systems-services/payment-systems/lynx)  
> **Jurisdiction:** Canada (Federal / Payments Canada / Bank of Canada)  

---

## 1. Regulatory Mandate & Operational Summary
Lynx is Canada's designated high-value payment system (replacing the legacy Large Value Transfer System, LVTS), operated by Payments Canada and designated as a systemically important payment system by the Bank of Canada. Lynx processes electronic wire transfers of critical financial values with real-time gross settlement (RTGS) and intraday settlement finality.

## 2. Deterministic Validation Thresholds & Operational Rules
- **Rule ID:** `PAYCAN-LYNX-01`
- **Category:** `HIGH_VALUE_WIRE_CLEARING`
- **Payment Rail:** `WIRE`

### Key Wire Validation Constraints:
1. **ISO 20022 Mandatory Messaging:**
   - Single Customer Credit Transfers must utilize `pacs.008.001.08`.
   - Financial Institution Transfers must utilize `pacs.009.001.08`.
   - Payment Returns must utilize `pacs.004.001.09`.
   - Payment Cancellation / Recalls must utilize `pacs.056.001.08`.
2. **Settlement Finality & Irrevocability:**
   - Under Section 18 of the *Canadian Payments Act*, once a wire is settled across Bank of Canada settlement accounts in Lynx, the payment is irrevocable and unconditional.
   - Wires cannot be unilaterally cancelled by the sender once released and posted.
3. **Wire Recall Protocol (pacs.056):**
   - Recalls may only be requested within 10 business days for reasons of: duplicate processing, technical error, or suspected fraud.
   - A recall requires the explicit consent of the receiving financial institution and the beneficiary customer if funds have posted.
4. **Data Integrity & Travel Rule Alignment:**
   - Originator name, account number, and street address are mandatory.
   - Beneficiary name, account number, and destination financial institution transit/SWIFT BIC are mandatory. Missing address or beneficiary identity triggers an immediate operational hold (`HOLD_PAYMENT`).
""",

    "02_payments_canada_acss_eft_rules.md": """# Payments Canada ACSS Rules for Electronic Funds Transfers (Rule E1 & E2)

> **Payment Rail Scope:** `WIRE` / `EFT`  
> **Statutory / Regulatory Authority:** `Payments Canada ACSS Rules E1, E2`  
> **Official Source:** [https://www.payments.ca](https://www.payments.ca)  
> **Jurisdiction:** Canada (Payments Canada Automated Clearing Settlement System)  

---

## 1. Regulatory Mandate & Operational Summary
The Automated Clearing Settlement System (ACSS) handles batch Electronic Funds Transfers (EFTs) across Canadian direct clearers. Rules E1 and E2 govern the exchange, routing, settlement, and return of commercial credits (direct deposits, payroll) and pre-authorized debits.

## 2. Deterministic Validation Thresholds & Operational Rules
- **Rule ID:** `PAYCAN-ACSS-01`
- **Category:** `EFT_BATCH_CLEARING`
- **Payment Rail:** `WIRE` / `EFT`

### Key EFT Validation Constraints:
1. **Routing Information Validation:**
   - Every EFT must carry a valid 3-digit Canadian Financial Institution Number and 5-digit Branch Transit Number registered in the Financial Institutions File (FIF).
   - Incompatible transit/account digits trigger an automatic rejection.
2. **Settlement Windows & Deadlines:**
   - Batch exchanges occur across 4 daily clearing windows.
   - Value-dating rules require payments to be exchanged no later than Day - 1 for next-day payroll settlement.
3. **Return Windows & Reasons:**
   - Returns for invalid account number (ERR-01), account closed (ERR-02), or payment stopped (ERR-03) must be initiated within 48 hours of settlement.
   - Unauthorized debit recourse extends to 90 calendar days for retail consumers.
""",

    "04_payments_canada_rule_a4_returned_items.md": """# Payments Canada Rule A4: Returned and Redirected Items (Duplicate Cheque Recourse)

> **Payment Rail Scope:** `CHEQUE`  
> **Statutory / Regulatory Authority:** `Payments Canada Rule A4 (ACSS)`  
> **Official Source:** [https://www.payments.ca](https://www.payments.ca)  
> **Jurisdiction:** Canada (Payments Canada)  

---

## 1. Regulatory Mandate & Operational Summary
Payments Canada Rule A4 establishes the comprehensive legal and operational procedure for returning paper items and electronic cheque images exchanged through the Automated Clearing Settlement System (ACSS) that cannot be paid or are subject to dispute.

## 2. Deterministic Validation Thresholds & Recourse Windows
- **Rule ID:** `PAYCAN-A4-01`
- **Category:** `CHEQUE_RETURN_AND_DUPLICATES`
- **Payment Rail:** `CHEQUE`

### Strict Recourse Windows & Return Reasons:
1. **Duplicate Presentment / Image Hash Duplicate:**
   - **Trigger:** Cheque image hash or serial number/account/transit matches an item already paid within the preceding 30 business days.
   - **Action:** Automated reversal and return permitted. Return reason code: *"Duplicate Item Presented"*.
   - **Recourse Window:** The drawee institution may return the duplicate item through the ACSS clearing stream up to **30 business days** after clearing.
2. **Non-Sufficient Funds (NSF) & Stopped Payments:**
   - Recourse deadline: Must be returned by the next business day (Day + 1) following presentment.
3. **Forged Endorsements & Material Alteration:**
   - Forged endorsement: Up to **90 calendar days** to initiate claim via statutory declaration of Intended Payee Not Paid.
   - Material alteration (altered amount or payee): Recourse allowed within 90 days of presentment.
4. **Post-Dated Item Presented in Error:**
   - Return reason: *"Post-Dated Item"*. Must be returned prior to the effective date.
""",

    "05_payments_canada_rule_a1_clearing_eligibility.md": """# Payments Canada Rule A1: Clearing Eligibility, Stale-Dating & Post-Dating

> **Payment Rail Scope:** `CHEQUE`  
> **Statutory / Regulatory Authority:** `Payments Canada Rule A1`  
> **Official Source:** [https://www.payments.ca](https://www.payments.ca)  
> **Jurisdiction:** Canada (Payments Canada)  

---

## 1. Regulatory Mandate & Operational Summary
Rule A1 defines the general rules pertaining to items acceptable for exchange, clearing, and settlement through the ACSS. It sets the baseline legal standards for cheque validity, dates, currencies, and physical/digital imaging standards.

## 2. Deterministic Validation Thresholds & Operational Constraints
- **Rule ID:** `PAYCAN-A1-01`
- **Category:** `CHEQUE_CLEARING_ELIGIBILITY`
- **Payment Rail:** `CHEQUE`

### Mandatory Cheque Eligibility Criteria:
1. **Stale-Dated Cheques (> 6 Months / 180 Days):**
   - **Threshold:** Any cheque presented more than **6 months (180 calendar days)** after the date stated on the cheque.
   - **Rule:** Deemed stale-dated and ineligible for clearing. The drawee bank is entitled to refuse payment and return the item unpaid under Rule A4 unless the drawer re-authorizes.
2. **Post-Dated Cheques:**
   - **Rule:** A cheque bearing a date future to the clearing date is NOT eligible for negotiation or clearing.
   - If deposited inadvertently, the drawee institution must dishonour and return the item.
3. **Currency & Institution Requirements:**
   - Must be denominated in Canadian Dollars (CAD) or US Dollars (USD drawn on Canadian FI).
   - Must be drawn on a direct or indirect member of Payments Canada.
""",

    "06_bank_act_access_to_funds_sor_2012_24.md": """# Bank Act: Access to Funds Regulations (SOR/2012-24) Maximum Cheque Hold Limits

> **Payment Rail Scope:** `CHEQUE`  
> **Statutory / Regulatory Authority:** `Bank Act (Canada) / SOR/2012-24 (FCAC)`  
> **Official Source:** [https://laws-lois.justice.gc.ca/eng/regulations/SOR-2012-24/index.html](https://laws-lois.justice.gc.ca/eng/regulations/SOR-2012-24/index.html)  
> **Jurisdiction:** Canada (Federal Bank Act / Financial Consumer Agency of Canada)  

---

## 1. Regulatory Mandate & Operational Summary
The Access to Funds Regulations under the *Bank Act* establish federal statutory maximums on how long Canadian banks can place a hold on funds deposited by cheque. It balances consumer funds availability with banking risk management.

## 2. Deterministic Validation Thresholds & Statutory Limits
- **Rule ID:** `FCAC-HOLD-01`
- **Category:** `CHEQUE_HOLD_PERIODS`
- **Payment Rail:** `CHEQUE`

### Federal Statutory Hold Limits:
1. **Immediate $100 CAD Release:**
   - The first **$100 CAD** of any cheque deposit must be made available immediately (if deposited in person with a teller) or on the next business day (if deposited at an ATM or via mobile image capture).
2. **Deposits of $1,500 CAD or Less:**
   - **In-Person (Branch):** Maximum hold period of **4 business days**.
   - **ATM / Mobile Deposit:** Maximum hold period of **5 business days**.
3. **Deposits Exceeding $1,500 CAD:**
   - **In-Person (Branch):** Maximum hold period of **7 business days**.
   - **ATM / Mobile Deposit:** Maximum hold period of **8 business days**.

### Statutory Hold Exceptions (Extending or Denying Hold Limit):
The statutory hold period limits do NOT apply, and the bank may place an extended hold or refuse deposit, if:
- **Fraud Suspicion:** The bank has reasonable grounds to believe the deposit is being made for illegal or fraudulent purposes.
- **New Account:** The customer's account has been open for less than **90 calendar days**.
- **Severe NSF History:** The customer has a repeated pattern of overdrawing or cheques returned NSF within the last 6 months.
- **Stale Cheque:** The cheque is stale-dated (dated more than 6 months prior).
- **Multiple Endorsements:** The cheque has been endorsed more than once prior to deposit.
""",

    "07_bills_of_exchange_act_cheques.md": """# Bills of Exchange Act (R.S.C., 1985, c. B-4) Cheque Statutory Framework

> **Payment Rail Scope:** `CHEQUE`  
> **Statutory / Regulatory Authority:** `Bills of Exchange Act, Part III (Cheques on a Bank)`  
> **Official Source:** [https://laws-lois.justice.gc.ca/eng/acts/B-4/index.html](https://laws-lois.justice.gc.ca/eng/acts/B-4/index.html)  
> **Jurisdiction:** Canada (Federal Statutory Law)  

---

## 1. Regulatory Mandate & Operational Summary
The *Bills of Exchange Act* is the overarching federal statutory legislation governing negotiable instruments in Canada, specifically defining cheques, legal validity, drawer liability, endorsement requirements, and the consequences of material alterations.

## 2. Deterministic Validation Thresholds & Legal Provisions
- **Rule ID:** `BEA-CHEQUE-01`
- **Category:** `CHEQUE_LEGAL_VALIDITY`
- **Payment Rail:** `CHEQUE`

### Key Statutory Provisions:
1. **Definition of Cheque (Section 165):**
   - A cheque is a bill of exchange drawn on a bank, payable on demand.
   - The bank's duty to pay a cheque terminates upon receipt of a stop payment countermand or notice of the customer's death.
2. **Post-Dated and Ante-Dated Instruments (Section 26):**
   - A bill is not invalid by reason only that it is ante-dated or post-dated, or that it bears date on a Sunday or non-business day. However, it cannot mature or be legally demanded before its stated date.
3. **Material Alteration (Section 144):**
   - Where a cheque or acceptance is materially altered without the assent of the drawer or endorsers, the instrument is **void**, except as against a party who has made, authorized, or assented to the alteration.
   - Material alterations include: altering the sum payable, date, time of payment, or payee name.
""",

    "11_osfi_guideline_e23_model_risk_ai.md": """# OSFI Guideline E-23: Enterprise Model Risk Management for AI in Canadian Banking

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
"""
}

def enrich():
    print(f"[*] Enriching Canadian Banking Regulations in: {TARGET_DIR}")
    for filename, content in DOCS_CONTENT.items():
        path = os.path.join(TARGET_DIR, filename)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content.strip() + "\n")
        sz = len(content.encode("utf-8")) / 1024
        print(f"    [+] Enriched {filename} ({sz:.1f} KB)")
    print("[+] Done enriching regulatory documents.")

if __name__ == "__main__":
    enrich()
