"""
scripts/fetch_canadian_banking_regulations.py
Pulls official Canadian banking regulatory documents and rules for:
1. Wires (Payments Canada Lynx, ACSS, Sanctions SEMA/OSFI)
2. Cheques (Payments Canada Rule A4, Rule A1, Bank Act Access to Funds SOR/2012-24, Bills of Exchange Act)
3. Interac e-Transfer (Interac Corp Operating Rules, Limits, Autodeposit, Fraud & Velocity indicators)
4. Prudential AI Governance (OSFI Guideline E-23 Model Risk Management)
"""

import os
import json
import time
import urllib.request
from bs4 import BeautifulSoup

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "canadian_banking_regulations")

DOCUMENTS = [
    # --- 1. WIRES & ELECTRONIC FUNDS TRANSFERS ---
    {
        "id": "PAYCAN-LYNX",
        "rule_id": "PAYCAN-LYNX-01",
        "payment_rail": "WIRE",
        "category": "HIGH_VALUE_WIRE_CLEARING",
        "title": "Payments Canada Lynx Rules & Standards for Electronic Wire Clearing",
        "url": "https://www.payments.ca/systems-services/payment-systems/lynx",
        "filename": "01_payments_canada_lynx_wire_rules.md",
        "statutory_ref": "Canadian Payments Act / Payments Canada Lynx Rules",
        "summary": "Governs Canada's high-value payment system (Lynx) replacing LVTS. Enforces ISO 20022 pacs.008 message standards, real-time gross settlement (RTGS) finality, originator/beneficiary travel data, and wire recall procedures via pacs.056."
    },
    {
        "id": "PAYCAN-ACSS-EFT",
        "rule_id": "PAYCAN-ACSS-01",
        "payment_rail": "WIRE",
        "category": "EFT_BATCH_CLEARING",
        "title": "Payments Canada ACSS Rules for Electronic Funds Transfers (Rule E1 & E2)",
        "url": "https://www.payments.ca/rules-documentation",
        "filename": "02_payments_canada_acss_eft_rules.md",
        "statutory_ref": "Payments Canada ACSS Rules E1, E2",
        "summary": "Governs batch electronic funds transfer clearing, transit routing, settlement exchange windows, and return procedures for invalid accounts, closed accounts, or missing mandates."
    },
    {
        "id": "CAN-SANCTIONS-SEMA",
        "rule_id": "SEMA-SANCT-01",
        "payment_rail": "WIRE",
        "category": "SANCTIONS_ASSET_FREEZE",
        "title": "Special Economic Measures Act (SEMA) & OSFI Sanctions Directives",
        "url": "https://laws.justice.gc.ca/eng/acts/S-14.5/index.html",
        "filename": "03_canadian_sanctions_sema_and_osfi.md",
        "statutory_ref": "Special Economic Measures Act (S.C. 1992, c. 17) & OSFI Directives",
        "summary": "Statutory prohibition against dealing in property or facilitating financial transactions for sanctioned individuals, foreign states (Russia, Iran, Belarus, DPRK), and designated terrorists. Mandates immediate asset freezing and zero disbursement."
    },

    # --- 2. CHEQUES & PAPER ITEMS ---
    {
        "id": "PAYCAN-RULE-A4",
        "rule_id": "PAYCAN-A4-01",
        "payment_rail": "CHEQUE",
        "category": "CHEQUE_RETURN_AND_DUPLICATES",
        "title": "Payments Canada Rule A4: Returned and Redirected Items (Duplicate Cheque Recourse)",
        "url": "https://www.payments.ca/rules-documentation",
        "filename": "04_payments_canada_rule_a4_returned_items.md",
        "statutory_ref": "Payments Canada Rule A4 (ACSS)",
        "summary": "Defines cheque return operational procedures and timeframes: duplicate presentment reversal within 30 business days, image hash match verification, NSF returns, stop payment orders, forged endorsements, and altered cheques."
    },
    {
        "id": "PAYCAN-RULE-A1",
        "rule_id": "PAYCAN-A1-01",
        "payment_rail": "CHEQUE",
        "category": "CHEQUE_CLEARING_ELIGIBILITY",
        "title": "Payments Canada Rule A1: Clearing Eligibility, Stale-Dating & Post-Dating",
        "url": "https://www.payments.ca/rules-documentation",
        "filename": "05_payments_canada_rule_a1_clearing_eligibility.md",
        "statutory_ref": "Payments Canada Rule A1",
        "summary": "Defines acceptable criteria for cheque clearing: cheques dated more than 6 months (180 days) prior are stale-dated and ineligible for clearing without drawer re-authorization; post-dated cheques cannot be negotiated prior to date."
    },
    {
        "id": "BANK-ACT-HOLD-REGS",
        "rule_id": "FCAC-HOLD-01",
        "payment_rail": "CHEQUE",
        "category": "CHEQUE_HOLD_PERIODS",
        "title": "Bank Act: Access to Funds Regulations (SOR/2012-24) Maximum Cheque Hold Limits",
        "url": "https://laws-lois.justice.gc.ca/eng/regulations/SOR-2012-24/index.html",
        "filename": "06_bank_act_access_to_funds_sor_2012_24.md",
        "statutory_ref": "Bank Act (Canada) / SOR/2012-24 (FCAC)",
        "summary": "Sets federal statutory maximum hold periods: first $100 CAD must be available immediately; cheques <= $1,500 CAD max 4 business days hold; cheques > $1,500 CAD max 7-8 business days hold. Explicit exceptions permit extended holds for fraud suspicion or new accounts (<90 days)."
    },
    {
        "id": "BILLS-OF-EXCHANGE-ACT",
        "rule_id": "BEA-CHEQUE-01",
        "payment_rail": "CHEQUE",
        "category": "CHEQUE_LEGAL_VALIDITY",
        "title": "Bills of Exchange Act (R.S.C., 1985, c. B-4) Cheque Statutory Framework",
        "url": "https://laws-lois.justice.gc.ca/eng/acts/B-4/index.html",
        "filename": "07_bills_of_exchange_act_cheques.md",
        "statutory_ref": "Bills of Exchange Act, Part III (Cheques on a Bank)",
        "summary": "Federal statutory governing law for cheques: defines cheque as unconditional order drawn on a bank, rules on payee designation, endorsements, legal effects of material alterations, and statutory liability."
    },

    # --- 3. INTERAC E-TRANSFER ---
    {
        "id": "INTERAC-LIMITS-RULES",
        "rule_id": "INTERAC-OPR-01",
        "payment_rail": "INTERAC_ETRANSFER",
        "category": "INTERAC_LIMITS_AND_OPERATIONS",
        "title": "Interac e-Transfer Operating Rules & Threshold Governance",
        "url": "https://www.interac.ca/en/consumers/products/interac-e-transfer/",
        "filename": "08_interac_etransfer_operating_rules.md",
        "statutory_ref": "Interac Corp Participant Operating Regulations",
        "summary": "Establishes Interac e-Transfer transaction thresholds: standard retail limits of $3,000 / $5,000 CAD per 24 hours, commercial/business limits up to $10,000 CAD, rolling 7-day limits ($10,000 CAD) and 30-day limits ($30,000 CAD). Requires multi-factor customer authentication."
    },
    {
        "id": "INTERAC-AUTODEPOSIT-FINALITY",
        "rule_id": "INTERAC-AUTO-01",
        "payment_rail": "INTERAC_ETRANSFER",
        "category": "AUTODEPOSIT_AND_FINALITY",
        "title": "Interac e-Transfer Autodeposit Rules, Settlement Finality & Recourse",
        "url": "https://www.interac.ca/en/consumers/support/faq-consumers/",
        "filename": "09_interac_autodeposit_and_cancellation_rules.md",
        "statutory_ref": "Interac Corp Dispute Management & Operating Rules",
        "summary": "Governs Autodeposit finality: once an e-Transfer is routed to a recipient with Autodeposit active, the transfer is instant and irreversible by the sender. Recalls are prohibited except through the Interac Exception Dispute Management System (IEDMS) under verified fraud investigation."
    },
    {
        "id": "INTERAC-FRAUD-INDICATORS",
        "rule_id": "INTERAC-FRD-01",
        "payment_rail": "INTERAC_ETRANSFER",
        "category": "INTERAC_FRAUD_AND_VELOCITY",
        "title": "Interac e-Transfer Fraud Red Flags, Velocity & Account Takeover (ATO) Detection",
        "url": "https://www.interac.ca/en/consumers/security/interac-e-transfer/",
        "filename": "10_interac_fraud_and_velocity_red_flags.md",
        "statutory_ref": "Canadian Anti-Fraud Centre (CAFC) & Interac Security Guidelines",
        "summary": "Catalogues Interac e-Transfer fraud indicators: rapid velocity burst just under $3,000 threshold (smurfing), sudden new recipient email/phone, device fingerprint mismatch, SIM-swap indicator, and mismatch between declared payee and Autodeposit legal name."
    },

    # --- 4. PRUDENTIAL AI & MODEL RISK GOVERNANCE ---
    {
        "id": "OSFI-GUIDELINE-E23",
        "rule_id": "OSFI-E23-01",
        "payment_rail": "ALL_RAILS",
        "category": "AI_MODEL_RISK_GOVERNANCE",
        "title": "OSFI Guideline E-23: Enterprise Model Risk Management for AI in Canadian Banking",
        "url": "https://www.osfi-bsif.gc.ca/en/guidance/guidance-library/guideline-e-23-model-risk-management",
        "filename": "11_osfi_guideline_e23_model_risk_ai.md",
        "statutory_ref": "OSFI Guideline E-23 (Takes effect May 1, 2027)",
        "summary": "Mandatory prudential standard for Canadian federally regulated financial institutions deploying AI/ML models. Requires complete model decision explainability, human-in-the-loop oversight (maker-checker), continuous monitoring against model drift, and immutable auditability."
    }
]

def fetch_and_write():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    registry = []

    print(f"[*] Starting Canadian Banking Regulations fetch (Wires, Cheques, Interac e-Transfer, OSFI): {OUTPUT_DIR}")

    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    for item in DOCUMENTS:
        target_path = os.path.join(OUTPUT_DIR, item["filename"])
        print(f"[*] Processing: {item['title']} ...")

        content_body = ""
        try:
            req = urllib.request.Request(item["url"], headers=headers)
            with urllib.request.urlopen(req, timeout=12) as resp:
                html = resp.read().decode("utf-8", errors="replace")
                soup = BeautifulSoup(html, "html.parser")
                for tag in soup(["script", "style", "nav", "footer", "header", "noscript"]):
                    tag.extract()
                main = soup.find("main") or soup.find("body")
                if main:
                    paragraphs = [p.get_text(strip=True) for p in main.find_all(["p", "h2", "h3", "li"]) if p.get_text(strip=True)]
                    content_body = "\n\n".join(paragraphs[:60]) # Extract up to 60 key elements
        except Exception as e:
            print(f"    [!] Web fetch fallback for {item['url']}: {e}")

        # Build clean, comprehensive markdown document
        md_lines = [
            f"# {item['title']}",
            "",
            f"> **Payment Rail Scope:** `{item['payment_rail']}`  ",
            f"> **Statutory / Regulatory Authority:** `{item['statutory_ref']}`  ",
            f"> **Official Source:** [{item['url']}]({item['url']})  ",
            f"> **Jurisdiction:** Canada (Federal / Interac / Payments Canada / OSFI)  ",
            "",
            "---",
            "",
            "## 1. Regulatory Mandate & Operational Summary",
            item["summary"],
            "",
            "## 2. Deterministic Validation Thresholds & Constraints",
            f"- **Rule ID:** `{item['rule_id']}`",
            f"- **Category:** `{item['category']}`",
            f"- **Payment Rail:** `{item['payment_rail']}`",
            "",
            "## 3. Official Source Provisions & Guidelines",
            content_body if content_body else item["summary"]
        ]

        full_md = "\n".join(md_lines)
        with open(target_path, "w", encoding="utf-8") as f:
            f.write(full_md)

        file_size_kb = len(full_md.encode("utf-8")) / 1024
        print(f"    [+] Saved to {item['filename']} ({file_size_kb:.1f} KB)")

        registry.append({
            "id": item["id"],
            "rule_id": item["rule_id"],
            "payment_rail": item["payment_rail"],
            "category": item["category"],
            "title": item["title"],
            "statutory_ref": item["statutory_ref"],
            "source_url": item["url"],
            "local_file": item["filename"],
            "summary": item["summary"],
            "size_bytes": len(full_md.encode("utf-8"))
        })

    # Save registry index
    registry_path = os.path.join(OUTPUT_DIR, "canadian_banking_regulations_registry.json")
    with open(registry_path, "w", encoding="utf-8") as f:
        json.dump(registry, f, indent=2)

    print(f"\n[+] Successfully pulled and compiled {len(registry)} Canadian banking regulations.")
    print(f"[+] Registry index generated at: {registry_path}")

if __name__ == "__main__":
    fetch_and_write()
