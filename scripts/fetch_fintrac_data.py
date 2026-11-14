"""
scripts/fetch_fintrac_data.py
Exhaustively pulls all FINTRAC compliance guidance directives and PCMLTFA statutory framework
documents from the official government sources into local structured markdown files.
"""

import os
import re
import json
import time
import urllib.request
from bs4 import BeautifulSoup

BASE_URL = "https://fintrac-canafe.canada.ca"
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "fintrac_policies")

DOCUMENTS_TO_FETCH = [
    # --- ACT & STATUTORY FRAMEWORK ---
    {
        "id": "PCMLTFA-STATUTE",
        "rule_id": "PCMLTFA-ACT-01",
        "category": "STATUTORY_FRAMEWORK",
        "title": "Proceeds of Crime (Money Laundering) and Terrorist Financing Act & Regulations",
        "path": "/act-loi/1-eng",
        "filename": "01_act_and_regulations_pcmltfa.md",
        "statutory_ref": "PCMLTFA S.C. 2000, c. 17",
        "core_mandate": "Governs statutory obligations for financial entities: customer identification, record keeping, reporting suspicious, large cash, and electronic funds transfers."
    },
    # --- TRANSACTION REPORTING DIRECTIVES ---
    {
        "id": "FINTRAC-STR",
        "rule_id": "FINTRAC-STR-01",
        "category": "SUSPICIOUS_TRANSACTION",
        "title": "Reporting Suspicious Transactions to FINTRAC",
        "path": "/guidance-directives/transaction-operation/str-dod/str-dod-eng",
        "filename": "02_suspicious_transactions_str.md",
        "statutory_ref": "PCMLTFA s. 7",
        "core_mandate": "Mandatory reporting of any completed or attempted transaction with reasonable grounds to suspect money laundering or terrorist financing. No dollar threshold."
    },
    {
        "id": "FINTRAC-LCTR",
        "rule_id": "FINTRAC-LCTR-01",
        "category": "LARGE_CASH_TRANSACTION",
        "title": "Reporting Large Cash Transactions to FINTRAC",
        "path": "/guidance-directives/transaction-operation/lctr-doie/lctr-doie-eng",
        "filename": "03_large_cash_transactions_lctr.md",
        "statutory_ref": "PCMLTFA s. 9",
        "core_mandate": "Mandatory reporting of receipt of $10,000 CAD or more in cash in a single transaction within 15 calendar days."
    },
    {
        "id": "FINTRAC-24HR",
        "rule_id": "FINTRAC-24HR-01",
        "category": "STRUCTURING_DETECTION",
        "title": "Reporting Transactions to FINTRAC: The 24-Hour Rule",
        "path": "/guidance-directives/transaction-operation/24hour/1-eng",
        "filename": "04_the_24_hour_rule.md",
        "statutory_ref": "PCMLTFA Regulations s. 126",
        "core_mandate": "Two or more cash or transfer transactions conducted within a rolling 24-hour window by or on behalf of the same person/entity totaling $10,000 or more must be aggregated and reported."
    },
    {
        "id": "FINTRAC-EFTR",
        "rule_id": "FINTRAC-EFTR-01",
        "category": "ELECTRONIC_FUNDS_TRANSFER",
        "title": "Reporting Electronic Funds Transfers to FINTRAC",
        "path": "/guidance-directives/transaction-operation/eft-dt/eft-dt-eng",
        "filename": "05_electronic_funds_transfers_eftr.md",
        "statutory_ref": "PCMLTFA s. 9.1",
        "core_mandate": "Mandatory reporting of international electronic funds transfers of $10,000 CAD or more sent or received in a single transaction (or aggregated over 24 hours)."
    },
    {
        "id": "FINTRAC-TRAVEL",
        "rule_id": "FINTRAC-TRAVEL-01",
        "category": "TRAVEL_RULE",
        "title": "Travel Rule for Electronic Funds and Virtual Currency Transfers",
        "path": "/guidance-directives/transaction-operation/travel-acheminement/1-eng",
        "filename": "06_travel_rule_eft_and_vc.md",
        "statutory_ref": "PCMLTFA Regulations s. 138-141",
        "core_mandate": "Mandates that originator and beneficiary identifying data (name, address, account number) must travel with the electronic transfer throughout the payment chain."
    },
    {
        "id": "FINTRAC-TPR",
        "rule_id": "FINTRAC-TPR-01",
        "category": "TERRORIST_PROPERTY",
        "title": "Reporting Listed Person or Entity Property to FINTRAC (Guide 5)",
        "path": "/guidance-directives/transaction-operation/Guide5/5-eng",
        "filename": "07_listed_person_and_terrorist_property.md",
        "statutory_ref": "PCMLTFA s. 7.1 & Criminal Code s. 83.05",
        "core_mandate": "Property in possession or control owned/controlled by or on behalf of a listed terrorist or group must be immediately reported and frozen. Zero funds may be disbursed."
    },
    {
        "id": "FINTRAC-LVCTR",
        "rule_id": "FINTRAC-LVCTR-01",
        "category": "VIRTUAL_CURRENCY_TRANSACTION",
        "title": "Reporting Large Virtual Currency Transactions to FINTRAC",
        "path": "/guidance-directives/transaction-operation/lvctr/lvctr-eng",
        "filename": "08_large_virtual_currency_transactions_lvctr.md",
        "statutory_ref": "PCMLTFA Regulations s. 127",
        "core_mandate": "Mandatory reporting of receipts of virtual currency equivalent to $10,000 CAD or more in a single transaction or aggregated under the 24-hour rule."
    },
    # --- KNOW YOUR CLIENT (KYC) & DUE DILIGENCE ---
    {
        "id": "FINTRAC-PEP",
        "rule_id": "FINTRAC-PEP-01",
        "category": "POLITICALLY_EXPOSED_PERSONS",
        "title": "Politically Exposed Persons and Heads of International Organizations (Account-Based)",
        "path": "/guidance-directives/client-clientele/pep/pep-acct-eng",
        "filename": "09_politically_exposed_persons_pep.md",
        "statutory_ref": "PCMLTFA s. 9.3",
        "core_mandate": "Requirement to identify Foreign/Domestic PEPs and HIOs, establish source of wealth/funds, and obtain senior management approval (four-eyes) before processing high-risk transactions."
    },
    {
        "id": "FINTRAC-ID-VERIFY",
        "rule_id": "FINTRAC-ID-01",
        "category": "IDENTITY_VERIFICATION",
        "title": "Methods to Verify the Identity of Persons and Entities (Guide 11)",
        "path": "/guidance-directives/client-clientele/Guide11/11-eng",
        "filename": "10_identity_verification_methods_guide11.md",
        "statutory_ref": "PCMLTFA Regulations s. 105-112",
        "core_mandate": "Prescribes valid government-issued photo ID, credit file, dual-process methods, and verification triggers ($3,000+ foreign exchange, $10,000+ transfers, suspicious attempts)."
    },
    {
        "id": "FINTRAC-BENEFICIAL-OWNERSHIP",
        "rule_id": "FINTRAC-BOR-01",
        "category": "BENEFICIAL_OWNERSHIP",
        "title": "Beneficial Ownership Requirements",
        "path": "/guidance-directives/client-clientele/bor-eng",
        "filename": "11_beneficial_ownership_requirements.md",
        "statutory_ref": "PCMLTFA Regulations s. 138",
        "core_mandate": "Mandatory identification and verification of every individual who directly or indirectly owns or controls 25% or more of an entity; prevents shell company obfuscation."
    },
    {
        "id": "FINTRAC-THIRD-PARTY",
        "rule_id": "FINTRAC-TPD-01",
        "category": "THIRD_PARTY_DETERMINATION",
        "title": "Third Party Determination Requirements",
        "path": "/guidance-directives/client-clientele/tpdr-eng",
        "filename": "12_third_party_determination.md",
        "statutory_ref": "PCMLTFA Regulations s. 136",
        "core_mandate": "Requirement to determine whether an account is opened or a $10,000+ transaction is conducted on behalf of a third party; record third party identity and relationship."
    },
    {
        "id": "FINTRAC-BUSINESS-RELATIONSHIP",
        "rule_id": "FINTRAC-BRR-01",
        "category": "BUSINESS_RELATIONSHIP",
        "title": "Business Relationship Requirements & Ongoing Monitoring",
        "path": "/guidance-directives/client-clientele/brr-eng",
        "filename": "13_business_relationship_requirements.md",
        "statutory_ref": "PCMLTFA Regulations s. 145-146",
        "core_mandate": "Obligation to monitor accounts periodically based on client risk rating, update client ID data, and detect transactions inconsistent with established client profile."
    },
    {
        "id": "FINTRAC-ONGOING-MONITORING",
        "rule_id": "FINTRAC-OMR-01",
        "category": "ONGOING_MONITORING",
        "title": "Ongoing Monitoring Requirements",
        "path": "/guidance-directives/client-clientele/omr-eng",
        "filename": "14_ongoing_monitoring_requirements.md",
        "statutory_ref": "PCMLTFA Regulations s. 147",
        "core_mandate": "Continuous monitoring of high-risk accounts and transactions to detect suspicious activity and ensure risk-mitigation measures are updated."
    },
    # --- SANCTIONS & MINISTERIAL DIRECTIVES ---
    {
        "id": "FINTRAC-SANCTIONS-EVASION",
        "rule_id": "FINTRAC-SANCT-01",
        "category": "SANCTIONS_ENFORCEMENT",
        "title": "Report Suspected Sanctions Evasion & Overview",
        "path": "/guidance-directives/transaction-operation/sanctions/sanctions-eng",
        "filename": "15_sanctions_evasion_overview.md",
        "statutory_ref": "Special Economic Measures Act (SEMA) & PCMLTFA s. 11.42",
        "core_mandate": "Prohibits transactions involving designated sanction targets, high-risk jurisdictions, and deceptive practices used to circumvent Canadian sanctions."
    },
    {
        "id": "FINTRAC-DIR-RUSSIA",
        "rule_id": "FINTRAC-DIR-RUS-01",
        "category": "MINISTERIAL_DIRECTIVE",
        "title": "Ministerial Directive on Financial Transactions Associated with Russia",
        "path": "/obligations/dir-rus-eng",
        "filename": "16_ministerial_directive_russia.md",
        "statutory_ref": "Ministerial Directive (Feb 24, 2024) under PCMLTFA s. 11.42",
        "core_mandate": "Mandatory enhanced due diligence on ALL financial transactions originating from or destined to Russia; requires identifying source of funds and ultimate beneficial owners."
    },
    {
        "id": "FINTRAC-DIR-IRAN",
        "rule_id": "FINTRAC-DIR-IRI-01",
        "category": "MINISTERIAL_DIRECTIVE",
        "title": "Ministerial Directive on Financial Transactions Associated with Iran",
        "path": "/obligations/dir-iri-eng",
        "filename": "17_ministerial_directive_iran.md",
        "statutory_ref": "Ministerial Directive under PCMLTFA s. 11.42",
        "core_mandate": "Comprehensive prohibition on financial transactions to or from Iran, Iranian financial institutions, and designated persons; transactions must be rejected/held."
    },
    {
        "id": "FINTRAC-DIR-DPRK",
        "rule_id": "FINTRAC-DIR-DPRK-01",
        "category": "MINISTERIAL_DIRECTIVE",
        "title": "Ministerial Directive on the Democratic People's Republic of Korea (DPRK)",
        "path": "/obligations/dir-dprk-eng",
        "filename": "18_ministerial_directive_dprk.md",
        "statutory_ref": "Ministerial Directive (Dec 9, 2017) under PCMLTFA s. 11.42",
        "core_mandate": "Total ban on financial transactions originating from, terminating in, or transiting through the DPRK (North Korea)."
    },
    # --- COMPLIANCE PROGRAM & RISK-BASED APPROACH ---
    {
        "id": "FINTRAC-COMPLIANCE-PROG",
        "rule_id": "FINTRAC-PROG-01",
        "category": "COMPLIANCE_PROGRAM",
        "title": "Compliance Program Requirements (Guide 4)",
        "path": "/guidance-directives/compliance-conformite/Guide4/4-eng",
        "filename": "19_compliance_program_requirements_guide4.md",
        "statutory_ref": "PCMLTFA Regulations s. 156",
        "core_mandate": "Mandates the five required pillars of an institutional compliance regime: appointed compliance officer, written policies/procedures, risk assessment, training, and 2-year effectiveness review."
    },
    {
        "id": "FINTRAC-RBA",
        "rule_id": "FINTRAC-RBA-01",
        "category": "RISK_BASED_APPROACH",
        "title": "Risk Assessment Guidance (Risk-Based Approach)",
        "path": "/guidance-directives/compliance-conformite/rba/rba-eng",
        "filename": "20_risk_based_approach_guidance.md",
        "statutory_ref": "PCMLTFA Regulations s. 156(1)(c)",
        "core_mandate": "Requires reporting entities to identify, assess, and document risks related to clients, business relationships, products, delivery channels, and geographic locations."
    },
    # --- RECORD KEEPING & OTHER BANKING REQUIREMENTS ---
    {
        "id": "FINTRAC-RECORD-KEEPING-FIN",
        "rule_id": "FINTRAC-REC-01",
        "category": "RECORD_KEEPING",
        "title": "Record Keeping Requirements for Financial Entities",
        "path": "/guidance-directives/recordkeeping-document/record/fin-eng",
        "filename": "21_record_keeping_financial_entities.md",
        "statutory_ref": "PCMLTFA Regulations s. 12-14",
        "core_mandate": "Mandates 5-year retention of large cash records, electronic funds transfer tickets, account opening records, signatures, and foreign exchange transaction tickets."
    },
    {
        "id": "FINTRAC-PREPAID",
        "rule_id": "FINTRAC-PREPAID-01",
        "category": "PREPAID_PRODUCTS",
        "title": "Prepaid Payment Product and Prepaid Product Accounts Requirements",
        "path": "/guidance-directives/prepaid-prepaye/1-eng",
        "filename": "22_prepaid_payment_products_and_accounts.md",
        "statutory_ref": "PCMLTFA Regulations s. 151-155",
        "core_mandate": "Extends KYC, verification, and monitoring rules to prepaid cards and stored-value products to eliminate anonymous reloadable payment risks."
    },
    {
        "id": "FINTRAC-CORRESPONDENT-BANKING",
        "rule_id": "FINTRAC-CORR-01",
        "category": "CORRESPONDENT_BANKING",
        "title": "Correspondent Banking Relationship Requirements",
        "path": "/guidance-directives/relationship-relation/1-eng",
        "filename": "23_correspondent_banking_requirements.md",
        "statutory_ref": "PCMLTFA s. 9.4",
        "core_mandate": "Requires enhanced due diligence, senior management approval, and prohibition against shell banks in international correspondent banking relationships."
    },
    {
        "id": "FINTRAC-FOREIGN-BRANCHES",
        "rule_id": "FINTRAC-BRANCH-01",
        "category": "FOREIGN_AFFILIATES",
        "title": "Foreign Branches, Foreign Subsidiaries and Affiliates Requirements",
        "path": "/guidance-directives/branches-succursales/1-eng",
        "filename": "24_foreign_branches_and_affiliates.md",
        "statutory_ref": "PCMLTFA s. 9.5",
        "core_mandate": "Mandates that reporting entities ensure foreign branches and subsidiaries apply policies and compliance standards consistent with PCMLTFA to the extent local law allows."
    },
    {
        "id": "FINTRAC-INDICATORS",
        "rule_id": "FINTRAC-IND-01",
        "category": "RED_FLAG_INDICATORS",
        "title": "Money Laundering and Terrorist Financing Indicators for Financial Entities",
        "path": "/guidance-directives/transaction-operation/indicators-indicateurs/fin_mltf-eng",
        "filename": "25_financial_entities_mltf_indicators.md",
        "statutory_ref": "FINTRAC Operational Red Flags",
        "core_mandate": "Catalogues transactional and behavioral red flags: rapid movement of funds, unverified beneficiaries, structuring under $10,000, inconsistent customer profile."
    },
    {
        "id": "FINTRAC-PENALTIES-AMP",
        "rule_id": "FINTRAC-AMP-01",
        "category": "ADMINISTRATIVE_PENALTIES",
        "title": "Penalties for Non-Compliance (Administrative Monetary Penalties)",
        "path": "/pen/1-eng",
        "filename": "26_administrative_monetary_penalties_amp.md",
        "statutory_ref": "PCMLTFA Part 4.1 & AMP Regulations",
        "core_mandate": "Specifies civil liability, violation classifications (minor, serious, very serious), and statutory penalties up to $500,000 per violation for failing to report or verify identity."
    }
]

def clean_html_to_markdown(html_content: str, source_url: str, title: str, statutory_ref: str) -> str:
    soup = BeautifulSoup(html_content, "html.parser")

    # Remove non-content elements
    for element in soup(["script", "style", "nav", "footer", "header", "noscript", ".wb-share", "#wb-bar", "#wb-lng"]):
        element.extract()

    main = soup.find("main") or soup.find("body") or soup

    lines = [
        f"# {title}",
        "",
        f"> **Statutory Reference:** `{statutory_ref}`  ",
        f"> **Official Source:** [{source_url}]({source_url})  ",
        f"> **Jurisdiction:** Canada (FINTRAC / CANAFE)  ",
        "",
        "---",
        ""
    ]

    for elem in main.find_all(["h1", "h2", "h3", "h4", "p", "ul", "ol", "table"]):
        if elem.name == "h1":
            continue
        elif elem.name == "h2":
            text = elem.get_text(strip=True)
            if text:
                lines.append(f"\n## {text}\n")
        elif elem.name == "h3":
            text = elem.get_text(strip=True)
            if text:
                lines.append(f"\n### {text}\n")
        elif elem.name == "h4":
            text = elem.get_text(strip=True)
            if text:
                lines.append(f"\n#### {text}\n")
        elif elem.name == "p":
            text = elem.get_text(strip=True)
            if text and not text.startswith("Date modified:"):
                lines.append(f"{text}\n")
        elif elem.name in ["ul", "ol"]:
            for li in elem.find_all("li", recursive=False):
                li_text = li.get_text(strip=True)
                if li_text:
                    lines.append(f"- {li_text}")
            lines.append("")
        elif elem.name == "table":
            rows = elem.find_all("tr")
            for i, row in enumerate(rows):
                cols = [td.get_text(strip=True).replace("\n", " ") for td in row.find_all(["th", "td"])]
                if cols:
                    lines.append("| " + " | ".join(cols) + " |")
                    if i == 0:
                        lines.append("| " + " | ".join(["---"] * len(cols)) + " |")
            lines.append("")

    return "\n".join(lines)

def fetch_all():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    registry = []

    print(f"[*] Starting EXHAUSTIVE FINTRAC compliance document fetch to: {OUTPUT_DIR}")

    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    for item in DOCUMENTS_TO_FETCH:
        full_url = BASE_URL + item["path"]
        target_path = os.path.join(OUTPUT_DIR, item["filename"])
        print(f"[*] Fetching: {item['title']} ...")
        
        try:
            req = urllib.request.Request(full_url, headers=headers)
            with urllib.request.urlopen(req, timeout=15) as resp:
                html = resp.read().decode("utf-8", errors="replace")
                
            md_content = clean_html_to_markdown(html, full_url, item["title"], item["statutory_ref"])
            
            with open(target_path, "w", encoding="utf-8") as f:
                f.write(md_content)
                
            file_size_kb = len(md_content.encode("utf-8")) / 1024
            print(f"    [+] Saved to {item['filename']} ({file_size_kb:.1f} KB)")

            registry.append({
                "id": item["id"],
                "rule_id": item["rule_id"],
                "category": item["category"],
                "title": item["title"],
                "statutory_ref": item["statutory_ref"],
                "source_url": full_url,
                "local_file": item["filename"],
                "core_mandate": item["core_mandate"],
                "size_bytes": len(md_content.encode("utf-8"))
            })

        except Exception as e:
            print(f"    [!] Error fetching {full_url}: {e}")
            fallback_md = f"# {item['title']}\n\n> **Statutory Reference:** `{item['statutory_ref']}`  \n> **Source:** [{full_url}]({full_url})  \n\n## Core Mandate\n{item['core_mandate']}\n"
            with open(target_path, "w", encoding="utf-8") as f:
                f.write(fallback_md)
            registry.append({
                "id": item["id"],
                "rule_id": item["rule_id"],
                "category": item["category"],
                "title": item["title"],
                "statutory_ref": item["statutory_ref"],
                "source_url": full_url,
                "local_file": item["filename"],
                "core_mandate": item["core_mandate"],
                "size_bytes": len(fallback_md.encode("utf-8"))
            })

        time.sleep(0.4)

    # Save registry index
    registry_path = os.path.join(OUTPUT_DIR, "fintrac_policy_registry.json")
    with open(registry_path, "w", encoding="utf-8") as f:
        json.dump(registry, f, indent=2)

    print(f"\n[+] Successfully pulled {len(registry)} exhaustive FINTRAC policy documents.")
    print(f"[+] Policy registry index generated at: {registry_path}")

if __name__ == "__main__":
    fetch_all()
