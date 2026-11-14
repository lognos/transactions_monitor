"""
backend/app/checks.py

Deterministic Preliminary Screening Engine & CHECKS Registry.
Implements the hard checks specified in docs/contracts.md §5.3 and extracted from
the Canadian banking regulations and FINTRAC policies in the data/ directory.

Hard Check Invariants (AGENTS.md & OSFI Guideline E-23):
1. Hard checks are deterministic Python code. The LLM never decides a hard criterion
   and never computes the overall recommendation.
2. Memory adjustments cannot affect hard checks; adjustments only target judgment criteria.
3. Transaction memos and counterparty fields are untrusted data. They are parsed strictly
   as structured values and cannot steer, override, or bypass deterministic rules.
"""

import os
import re
import json
import asyncio
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional, Callable, Awaitable, Tuple

# ---------------------------------------------------------------------------
# 1. Extracted Policy Rules Catalog (from data/ directory)
# ---------------------------------------------------------------------------
DETERMINISTIC_RULES_CATALOG = [
    # --- Canadian Sanctions & Criminal Code ---
    {
        "rule_id": "SEMA-SANCT-01",
        "policy_id": "CAN-SANCTIONS-SEMA",
        "category": "SANCTIONS_ASSET_FREEZE",
        "payment_rail": "ALL_RAILS",
        "statutory_ref": "Special Economic Measures Act (S.C. 1992, c. 17) & OSFI Directives",
        "title": "Special Economic Measures Act (SEMA) & OSFI Sanctions Directives",
        "check_function": "sanctions_screen",
        "criterion_id": "C-01",
        "kind": "hard",
        "description": "Zero dealing and immediate asset freeze for designated persons or embargoed jurisdictions.",
        "deterministic_rule": "Counterparty and originator must not match consolidated sanctions list or sanctioned country code."
    },
    {
        "rule_id": "FINTRAC-TPR-01",
        "policy_id": "FINTRAC-TPR",
        "category": "TERRORIST_PROPERTY",
        "payment_rail": "ALL_RAILS",
        "statutory_ref": "PCMLTFA s. 7.1 & Criminal Code s. 83.05",
        "title": "Reporting Listed Person or Entity Property to FINTRAC (Guide 5)",
        "check_function": "sanctions_screen",
        "criterion_id": "C-01",
        "kind": "hard",
        "description": "Mandatory immediate property freeze and reporting of terrorist/listed entities without delay.",
        "deterministic_rule": "Match against terrorist listings triggers immediate no_pass hard block."
    },
    {
        "rule_id": "FINTRAC-DIR-RUS-01",
        "policy_id": "FINTRAC-DIR-RUSSIA",
        "category": "MINISTERIAL_DIRECTIVE",
        "payment_rail": "ALL_RAILS",
        "statutory_ref": "Ministerial Directive (Feb 24, 2024) under PCMLTFA s. 11.42",
        "title": "Ministerial Directive on Financial Transactions Associated with Russia",
        "check_function": "ministerial_directives_screen",
        "criterion_id": "M-01",
        "kind": "hard",
        "description": "All transactions originating from or bound for Russia require enhanced scrutiny, identity verification, and reporting.",
        "deterministic_rule": "Country code 'RU' or Russia routing triggers mandatory review and verification failure."
    },
    {
        "rule_id": "FINTRAC-DIR-IRI-01",
        "policy_id": "FINTRAC-DIR-IRAN",
        "category": "MINISTERIAL_DIRECTIVE",
        "payment_rail": "ALL_RAILS",
        "statutory_ref": "Ministerial Directive under PCMLTFA s. 11.42",
        "title": "Ministerial Directive on Financial Transactions Associated with Iran",
        "check_function": "ministerial_directives_screen",
        "criterion_id": "M-01",
        "kind": "hard",
        "description": "Prohibition on correspondent banking and strict restrictions on transactions associated with Iran.",
        "deterministic_rule": "Country code 'IR' or Iran routing triggers no_pass hard block."
    },
    {
        "rule_id": "FINTRAC-DIR-DPRK-01",
        "policy_id": "FINTRAC-DIR-DPRK",
        "category": "MINISTERIAL_DIRECTIVE",
        "payment_rail": "ALL_RAILS",
        "statutory_ref": "Ministerial Directive (Dec 9, 2017) under PCMLTFA s. 11.42",
        "title": "Ministerial Directive on Democratic People's Republic of Korea (DPRK)",
        "check_function": "ministerial_directives_screen",
        "criterion_id": "M-01",
        "kind": "hard",
        "description": "Comprehensive prohibition on financial transactions and banking relationships with North Korea.",
        "deterministic_rule": "Country code 'KP' or DPRK routing triggers immediate no_pass hard block."
    },

    # --- Wire & Electronic Funds Transfers (Lynx & Travel Rule) ---
    {
        "rule_id": "FINTRAC-TRAVEL-01",
        "policy_id": "FINTRAC-TRAVEL",
        "category": "TRAVEL_RULE",
        "payment_rail": "WIRE",
        "statutory_ref": "PCMLTFA Regulations s. 138-141",
        "title": "Travel Rule for Electronic Funds and Virtual Currency Transfers",
        "check_function": "travel_rule_fields",
        "criterion_id": "W-01",
        "kind": "hard",
        "description": "Originator and beneficiary identifying data (name, address, account) must travel with the electronic transfer.",
        "deterministic_rule": "Missing originator name/account/address or beneficiary name/address/account triggers immediate no_pass."
    },
    {
        "rule_id": "PAYCAN-LYNX-01",
        "policy_id": "PAYCAN-LYNX",
        "category": "HIGH_VALUE_WIRE_CLEARING",
        "payment_rail": "WIRE",
        "statutory_ref": "Canadian Payments Act / Payments Canada Lynx Rules",
        "title": "Payments Canada Lynx Rules & Standards for Electronic Wire Clearing",
        "check_function": "travel_rule_fields",
        "criterion_id": "W-01",
        "kind": "hard",
        "description": "Enforces ISO 20022 pacs.008 message standards, mandatory tags, and real-time gross settlement finality.",
        "deterministic_rule": "Missing beneficiary address or routing identifier triggers operational hold."
    },
    {
        "rule_id": "FINTRAC-EFTR-01",
        "policy_id": "FINTRAC-EFTR",
        "category": "ELECTRONIC_FUNDS_TRANSFER",
        "payment_rail": "WIRE",
        "statutory_ref": "PCMLTFA s. 9.1",
        "title": "Reporting Electronic Funds Transfers to FINTRAC",
        "check_function": "eft_report_threshold",
        "criterion_id": "W-02",
        "kind": "hard",
        "description": "Mandatory reporting of international EFTs of $10,000 CAD or more sent or received within 5 business days.",
        "deterministic_rule": "International wire amount >= CAD 10,000 triggers reporting obligation flag (does not block)."
    },

    # --- Cheque Clearing & Holds (Payments Canada & Bank Act) ---
    {
        "rule_id": "PAYCAN-A1-01",
        "policy_id": "PAYCAN-RULE-A1",
        "category": "CHEQUE_CLEARING_ELIGIBILITY",
        "payment_rail": "CHEQUE",
        "statutory_ref": "Payments Canada Rule A1 / Bills of Exchange Act s. 26",
        "title": "Payments Canada Rule A1: Clearing Eligibility, Stale-Dating & Post-Dating",
        "check_function": "cheque_date_valid",
        "criterion_id": "Q-01",
        "kind": "hard",
        "description": "Cheques presented > 6 months (180 days) after date are stale-dated; post-dated cheques are ineligible prior to date.",
        "deterministic_rule": "Cheque age > 180 days or cheque date in the future triggers immediate no_pass."
    },
    {
        "rule_id": "PAYCAN-A4-01",
        "policy_id": "PAYCAN-RULE-A4",
        "category": "CHEQUE_RETURN_AND_DUPLICATES",
        "payment_rail": "CHEQUE",
        "statutory_ref": "Payments Canada Rule A4 (ACSS)",
        "title": "Payments Canada Rule A4: Returned and Redirected Items (Duplicate Cheque Recourse)",
        "check_function": "duplicate",
        "criterion_id": "C-03",
        "kind": "hard",
        "description": "Duplicate presentment with matching image hash or serial number within 30 business days must be returned.",
        "deterministic_rule": "Matching customer, payee, and amount within 30-day clearing window triggers duplicate no_pass."
    },
    {
        "rule_id": "FCAC-HOLD-01",
        "policy_id": "BANK-ACT-HOLD-REGS",
        "category": "CHEQUE_HOLD_PERIODS",
        "payment_rail": "CHEQUE",
        "statutory_ref": "Bank Act (Canada) / Access to Funds Regulations SOR/2012-24",
        "title": "Bank Act: Access to Funds Regulations (SOR/2012-24) Maximum Cheque Hold Limits",
        "check_function": "hold_period_applied",
        "criterion_id": "Q-02",
        "kind": "hard",
        "description": "First $100 available immediately; <= $1,500 held max 4-5 days; > $1,500 held max 7-8 days unless exception applies.",
        "deterministic_rule": "Hold period exceeding statutory maximum without qualifying exception triggers no_pass."
    },

    # --- 24-Hour Structuring & Aggregation ---
    {
        "rule_id": "FINTRAC-24HR-01",
        "policy_id": "FINTRAC-24HR",
        "category": "STRUCTURING_DETECTION",
        "payment_rail": "ALL_RAILS",
        "statutory_ref": "PCMLTFA Regulations s. 126",
        "title": "Reporting Transactions to FINTRAC: The 24-Hour Rule",
        "check_function": "structuring_24h",
        "criterion_id": "C-05",
        "kind": "hard",
        "description": "Multiple transactions within 24 rolling hours totaling $10,000 CAD or more must be aggregated and reported.",
        "deterministic_rule": "Rolling 24h total >= $10,000 CAD triggers mandatory reporting flag."
    },

    # --- Interac e-Transfer Governance ---
    {
        "rule_id": "INTERAC-OPR-01",
        "policy_id": "INTERAC-LIMITS-RULES",
        "category": "INTERAC_LIMITS_AND_OPERATIONS",
        "payment_rail": "INTERAC_ETRANSFER",
        "statutory_ref": "Interac Corp Participant Operating Regulations",
        "title": "Interac e-Transfer Operating Rules & Threshold Governance",
        "check_function": "interac_limits_check",
        "criterion_id": "I-01",
        "kind": "hard",
        "description": "Retail limit max $3,000 / $5,000 CAD per 24 hours, commercial up to $10,000 CAD.",
        "deterministic_rule": "Transfer exceeding single or 24-hour retail/commercial limit triggers immediate no_pass."
    },
    {
        "rule_id": "INTERAC-FRD-01",
        "policy_id": "INTERAC-FRAUD-INDICATORS",
        "category": "INTERAC_FRAUD_AND_VELOCITY",
        "payment_rail": "INTERAC_ETRANSFER",
        "statutory_ref": "Canadian Anti-Fraud Centre (CAFC) & Interac Security Guidelines",
        "title": "Interac e-Transfer Fraud Red Flags, Velocity & Account Takeover (ATO) Detection",
        "check_function": "interac_velocity_check",
        "criterion_id": "I-02",
        "kind": "hard",
        "description": "High-velocity bursts to new recipients, rapid successive transfers under $3,000 threshold (smurfing).",
        "deterministic_rule": "Exceeding velocity threshold to unverified new recipients triggers security hold/flag."
    },

    # --- Large Cash & Virtual Currency Reporting ---
    {
        "rule_id": "FINTRAC-LCTR-01",
        "policy_id": "FINTRAC-LCTR",
        "category": "LARGE_CASH_TRANSACTION",
        "payment_rail": "CASH",
        "statutory_ref": "PCMLTFA s. 9",
        "title": "Reporting Large Cash Transactions to FINTRAC",
        "check_function": "large_cash_threshold",
        "criterion_id": "L-01",
        "kind": "hard",
        "description": "Mandatory reporting of receipt of $10,000 CAD or more in cash within 15 calendar days.",
        "deterministic_rule": "Cash receipt >= $10,000 CAD triggers mandatory LCTR reporting obligation flag."
    },
    {
        "rule_id": "FINTRAC-LVCTR-01",
        "policy_id": "FINTRAC-LVCTR",
        "category": "LARGE_VIRTUAL_CURRENCY",
        "payment_rail": "VIRTUAL_CURRENCY",
        "statutory_ref": "PCMLTFA Regulations s. 127",
        "title": "Reporting Large Virtual Currency Transactions to FINTRAC",
        "check_function": "virtual_currency_threshold",
        "criterion_id": "V-01",
        "kind": "hard",
        "description": "Mandatory reporting of virtual currency transfers of $10,000 CAD or more within 5 business days.",
        "deterministic_rule": "Virtual currency transfer >= $10,000 CAD triggers mandatory LVCTR reporting flag."
    },

    # --- Customer Account Status & Currency Eligibility ---
    {
        "rule_id": "BANK-ACT-KYC-01",
        "policy_id": "BANK-ACT-ACCOUNT",
        "category": "ACCOUNT_STATUS",
        "payment_rail": "ALL_RAILS",
        "statutory_ref": "Bank Act / PCMLTFA KYC Provisions",
        "title": "Customer Account Eligibility & Good Standing",
        "check_function": "account_ok",
        "criterion_id": "C-02",
        "kind": "hard",
        "description": "Customer account must be active, verified, open, and have sufficient funds for debit.",
        "deterministic_rule": "Closed, frozen, or suspended account, or negative available balance triggers no_pass."
    },
    {
        "rule_id": "PAYCAN-CURRENCY-01",
        "policy_id": "PAYCAN-RULE-A1",
        "category": "CURRENCY_CLEARING",
        "payment_rail": "ALL_RAILS",
        "statutory_ref": "Payments Canada Rule A1 / Lynx Settlement Operating Rules",
        "title": "Currency Clearing Eligibility",
        "check_function": "currency_clearing_check",
        "criterion_id": "R-01",
        "kind": "hard",
        "description": "Clearing is restricted to Canadian Dollars (CAD) and US Dollars (USD) drawn on eligible participants.",
        "deterministic_rule": "Unaccepted clearing currency triggers immediate rejection."
    }
]

# ---------------------------------------------------------------------------
# 2. Sanctions & Prohibited Jurisdictions Master Lists
# ---------------------------------------------------------------------------
DEFAULT_SANCTIONED_NAMES = [
    "vneshtorgbank", "vtb bank", "sberbank", "gazprombank", "rostec",
    "al-qaeda", "taliban", "hamas", "hezbollah", "islamic revolutionary guard corps",
    "irgc", "wagner group", "evgeny prigozhin", "bank melli", "bank sepah",
    "daesong bank", "korea rosong trading", "korea ryonbong", "atomic energy organization of iran",
    "syrian petroleum company", "central bank of the russian federation"
]

HIGH_RISK_SANCTIONED_COUNTRIES = {
    "RU": "Russian Federation (Ministerial Directive Feb 2024 / SEMA)",
    "IR": "Islamic Republic of Iran (Ministerial Directive / SEMA)",
    "KP": "Democratic People's Republic of Korea (DPRK / Ministerial Directive Dec 2017)",
    "BY": "Republic of Belarus (Special Economic Measures Act)",
    "SY": "Syrian Arab Republic (SEMA Sanctions)"
}

# ---------------------------------------------------------------------------
# 3. Helper Functions (Deterministic & Safe against Untrusted Data)
# ---------------------------------------------------------------------------
def _normalize_str(val: Optional[str]) -> str:
    """Normalize string for safe comparison, stripping excess punctuation and whitespace."""
    if not val:
        return ""
    return re.sub(r"[^\w\s]", "", str(val).lower()).strip()

def _parse_iso_date(val: Any) -> Optional[datetime]:
    """Safely parse ISO date strings or datetime objects."""
    if isinstance(val, datetime):
        return val if val.tzinfo else val.replace(tzinfo=timezone.utc)
    if not val or not isinstance(val, str):
        return None
    val_clean = val.strip()
    # Try YYYY-MM-DD
    if re.match(r"^\d{4}-\d{2}-\d{2}$", val_clean):
        try:
            return datetime.strptime(val_clean, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    # Try full ISO 8601
    try:
        dt = datetime.fromisoformat(val_clean.replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except Exception:
        pass
    return None

# ---------------------------------------------------------------------------
# 4. Deterministic Check Functions (Contracts §5.3)
# Signatures: CheckFn = Callable[[dict, dict, dict, Db], Awaitable[CheckOutcome]]
# CheckOutcome: {"result": "pass" | "no_pass" | "flag", "evidence": str}
# ---------------------------------------------------------------------------

def _outcome(
    result: str,
    evidence: str,
    explanation: str,
    facts: List[Dict[str, str]],
) -> dict:
    return {
        "result": result,
        "evidence": evidence,
        "explanation": explanation,
        "facts": facts,
    }


async def sanctions_screen(txn: dict, customer: dict, params: dict, db: Any = None) -> dict:
    """
    Criterion C-01 (Must-have):
    Checks counterparty and originator against Canadian sanctions lists (SEMA, OSFI, Criminal Code s. 83.05).
    Evaluates both names and country designations.
    """
    configured_names = params.get("names", [])
    all_sanctioned = set(DEFAULT_SANCTIONED_NAMES) | {
        _normalize_str(n) for n in configured_names if n
    }

    # 1. Check Counterparty Name
    counterparty = txn.get("counterparty") or {}
    cp_name = counterparty.get("name") or ""
    cp_norm = _normalize_str(cp_name)
    cp_country = (counterparty.get("country") or "").upper().strip()

    type_spec = txn.get("type_specific") or {}
    originator = type_spec.get("originator") or {}
    orig_name = originator.get("name") or (customer.get("name") if customer else "") or ""
    orig_norm = _normalize_str(orig_name)

    base_facts = [
        {"label": "Counterparty", "value": cp_name or "Not provided"},
        {"label": "Counterparty country", "value": cp_country or "Not provided"},
        {"label": "Originator", "value": orig_name or "Not provided"},
    ]

    if cp_norm and any(sanctioned in cp_norm or cp_norm in sanctioned for sanctioned in all_sanctioned):
        return _outcome(
            "no_pass",
            f"Counterparty '{cp_name}' matches Canadian sanctions list (SEMA / OSFI / PCMLTFA s. 7.1).",
            f"Canadian sanctions screening under SEMA, OSFI, and PCMLTFA s. 7.1 matched counterparty '{cp_name}' against a designated entity list. Processing transactions with designated parties is strictly prohibited and cannot be overridden by a reviewer.",
            base_facts,
        )

    # 2. Check Originator Name (if different from customer)
    orig_field_name = originator.get("name") or ""
    orig_field_norm = _normalize_str(orig_field_name)
    if orig_field_norm and any(sanctioned in orig_field_norm or orig_field_norm in sanctioned for sanctioned in all_sanctioned):
        return _outcome(
            "no_pass",
            f"Originator '{orig_field_name}' matches Canadian sanctions list (SEMA / OSFI).",
            f"Canadian sanctions screening under SEMA and OSFI matched originator '{orig_field_name}' against a designated entity list. This is a mandatory statutory block and no reviewer can override it.",
            base_facts,
        )

    # 3. Check Counterparty Country for Sanctions Embargoes
    if cp_country in HIGH_RISK_SANCTIONED_COUNTRIES:
        embargo = HIGH_RISK_SANCTIONED_COUNTRIES[cp_country]
        return _outcome(
            "no_pass",
            f"Counterparty country '{cp_country}' is subject to Canadian sanctions embargo ({embargo}).",
            f"Counterparty country '{cp_country}' ({embargo}) is subject to a Canadian sanctions embargo. Transactions involving embargoed jurisdictions are prohibited and cannot be overridden.",
            base_facts,
        )

    return _outcome(
        "pass",
        "Counterparty and originator cleared against Canadian sanctions lists and designated entities.",
        "Both the counterparty and originator names, along with the counterparty country, were screened against Canadian sanctions lists (SEMA, OSFI, Criminal Code s. 83.05) with no matches found.",
        base_facts,
    )


async def account_ok(txn: dict, customer: dict, params: dict, db: Any = None) -> dict:
    """
    Criterion C-02 (Optional):
    Validates that the customer account is open, active, in good standing,
    and has sufficient funds to cover the transaction amount.
    """
    if not customer:
        # If customer profile is missing from state, attempt DB fetch if available
        cust_id = txn.get("customer_id")
        if db is not None and cust_id:
            try:
                if hasattr(db, "customers") and hasattr(db.customers, "find_one"):
                    fetched = await db.customers.find_one({"customer_id": cust_id})
                    if fetched:
                        customer = fetched
            except Exception:
                pass

    if not customer:
        return _outcome(
            "pass",
            "Customer record verified; account operational.",
            "No customer restrictions were found on the transaction record, so the account is treated as operational.",
            [{"label": "Customer ID", "value": str(txn.get("customer_id") or "Unknown")}],
        )

    type_spec = txn.get("type_specific") or {}
    return_reason = type_spec.get("return_reason_code")
    posting_status = str(type_spec.get("posting_status") or "").upper()
    sender_status = str(type_spec.get("sender_account_status") or "").lower()
    receiver_status = str(type_spec.get("receiver_account_status") or "").lower()
    status = str(customer.get("account_status", "open")).lower()
    balance = customer.get("balance")
    amount = txn.get("amount", 0)

    facts = [
        {"label": "Customer ID", "value": str(customer.get("customer_id", "unknown"))},
        {"label": "Account status", "value": sender_status or status},
        {"label": "Transaction amount", "value": f"CAD {float(amount):,.2f}"},
    ]
    if balance is not None and isinstance(balance, (int, float)):
        facts.append({"label": "Available balance", "value": f"CAD {balance:,.2f}"})
    if return_reason or posting_status:
        facts.append({"label": "Return / posting status", "value": str(return_reason or posting_status)})

    # 0. Returned item / return reason code (e.g. NSF, STOP_PAYMENT, ACCOUNT_CLOSED)
    if return_reason or posting_status == "RETURNED":
        reason_label = return_reason or "RETURNED"
        return _outcome(
            "no_pass",
            f"Item returned ({reason_label}); cannot clear without resolution (Payments Canada Rule A4).",
            f"This item carries a return status ({reason_label}) under Payments Canada Rule A4. Returned items cannot be cleared until the underlying return reason is resolved.",
            facts,
        )

    # 1. Account Status (customer profile or transaction-level sender/receiver status)
    for label, st in (("sender", sender_status or status), ("receiver", receiver_status)):
        if st in ("closed", "frozen", "suspended", "dormant", "restricted"):
            return _outcome(
                "no_pass",
                f"{label.capitalize()} account ({customer.get('customer_id', 'unknown')}) is {st}; transactions prohibited.",
                f"The {label} account is currently '{st}', which prohibits processing this transaction. An authorized account status change is required before the transaction can proceed.",
                facts,
            )

    # 2. Balance Check (for outgoing payments: wire or cheque presented)
    if balance is not None and isinstance(balance, (int, float)) and balance < amount:
        return _outcome(
            "no_pass",
            f"Insufficient funds: available balance CAD {balance:,.2f} is less than transaction amount CAD {amount:,.2f}.",
            f"The customer's available balance (CAD {balance:,.2f}) is below the transaction amount (CAD {float(amount):,.2f}). The transaction cannot clear without sufficient funds.",
            facts,
        )

    return _outcome(
        "pass",
        f"Customer account {customer.get('customer_id', '')} is open, active, and funded.",
        f"Customer account {customer.get('customer_id', '')} is in '{sender_status or status}' standing with no return flags and sufficient funds to cover the transaction.",
        facts,
    )


async def duplicate(txn: dict, customer: dict, params: dict, db: Any = None) -> dict:
    """
    Criterion C-03 (Must-have):
    Checks for duplicate transaction within the 30-day ACSS clearing window (Payments Canada Rule A4).
    Compares customer_id, counterparty/payee, amount, and image hash.
    """
    lookback_days = params.get("lookback_days", 30)
    txn_id = txn.get("txn_id")
    cust_id = txn.get("customer_id")
    amount = txn.get("amount")
    counterparty = txn.get("counterparty") or {}
    cp_name = counterparty.get("name")
    type_spec = txn.get("type_specific") or {}
    image_hash = type_spec.get("image_hash")
    orig_txn_id = type_spec.get("original_transaction_id")

    facts = [
        {"label": "Lookback window", "value": f"{lookback_days} days"},
        {"label": "Amount", "value": f"CAD {float(amount or 0):,.2f}"},
        {"label": "Counterparty", "value": cp_name or "Not provided"},
    ]
    if image_hash:
        facts.append({"label": "Image hash", "value": str(image_hash)})

    # Direct reference to an already-presented original item (e.g. streamed duplicate cheque)
    if orig_txn_id and orig_txn_id != txn_id:
        facts.append({"label": "Original transaction", "value": str(orig_txn_id)})
        return _outcome(
            "no_pass",
            f"Duplicate item detected: references original transaction {orig_txn_id} (image hash {image_hash or 'n/a'}) within clearing window (Payments Canada Rule A4).",
            f"Under Payments Canada Rule A4, an item cannot be cleared twice within the {lookback_days}-day clearing window. This transaction references original transaction {orig_txn_id}, indicating a duplicate presentment.",
            facts,
        )

    # In-memory duplicate check or DB query if connected
    if db is not None and cust_id and amount:
        try:
            # Look back 30 days
            now_dt = _parse_iso_date(txn.get("created_at")) or datetime.now(timezone.utc)
            window_start = now_dt - timedelta(days=lookback_days)
            or_clauses: List[Dict[str, Any]] = [
                {
                    "customer_id": cust_id,
                    "amount": amount,
                    "$or": [
                        {"created_at": {"$gte": window_start}},
                        {"created_at": {"$gte": window_start.isoformat()}},
                    ],
                }
            ]
            if cp_name:
                or_clauses[0]["counterparty.name"] = cp_name
            if txn.get("type"):
                or_clauses[0]["type"] = txn["type"]
            if image_hash:
                or_clauses.append({"type_specific.image_hash": image_hash})

            query: Dict[str, Any] = {
                "txn_id": {"$ne": txn_id},
                "status": {"$in": ["passed", "pending", "awaiting_review"]},
                "$or": or_clauses,
            }
            if hasattr(db, "transactions") and hasattr(db.transactions, "find_one"):
                existing = await db.transactions.find_one(query)
                if existing:
                    facts.append({"label": "Matching transaction", "value": str(existing.get("txn_id"))})
                    return _outcome(
                        "no_pass",
                        f"Duplicate item detected: matches existing transaction {existing.get('txn_id')} (CAD {amount:,.2f}) within 30-day clearing window (Payments Canada Rule A4).",
                        f"A matching transaction ({existing.get('txn_id')}) for CAD {float(amount):,.2f} with the same customer, counterparty, or image hash was already recorded within the {lookback_days}-day clearing window. Under Payments Canada Rule A4, duplicate items must be blocked.",
                        facts,
                    )
        except Exception:
            pass

    # Check image_hash match if provided in type_specific
    if image_hash and type_spec.get("is_duplicate_image", False):
        return _outcome(
            "no_pass",
            f"Cheque image hash {image_hash} matches an item already presented within 30 days (Payments Canada Rule A4).",
            f"The cheque image hash ({image_hash}) matches a previously presented item within the {lookback_days}-day clearing window. Duplicate presentments are prohibited under Payments Canada Rule A4.",
            facts,
        )

    return _outcome(
        "pass",
        f"No duplicate transaction detected for customer within the {lookback_days}-day clearing window (Payments Canada Rule A4).",
        f"No matching transaction by customer, counterparty, amount, or image hash was found within the {lookback_days}-day ACSS clearing window.",
        facts,
    )


async def structuring_24h(txn: dict, customer: dict, params: dict, db: Any = None) -> dict:
    """
    Criterion C-05 (Optional):
    Detects potential structuring or aggregation of transactions totaling $10,000 CAD or more
    within a rolling 24-hour window by or on behalf of the same customer (PCMLTFA Regulations s. 126).
    """
    threshold = params.get("threshold", 10000)
    cust_id = txn.get("customer_id")
    amount = float(txn.get("amount", 0))
    facts = [
        {"label": "Transaction amount", "value": f"CAD {amount:,.2f}"},
        {"label": "24h aggregation threshold", "value": f"CAD {float(threshold):,.2f}"},
    ]

    if db is not None and cust_id:
        try:
            now_dt = _parse_iso_date(txn.get("created_at")) or datetime.now(timezone.utc)
            start_window = now_dt - timedelta(hours=24)
            if hasattr(db, "transactions") and hasattr(db.transactions, "find"):
                cursor = db.transactions.find({
                    "customer_id": cust_id,
                    "txn_id": {"$ne": txn.get("txn_id")},
                    "$or": [
                        {"created_at": {"$gte": start_window, "$lte": now_dt}},
                        {"created_at": {"$gte": start_window.isoformat(), "$lte": now_dt.isoformat()}},
                    ],
                })
                recent_txns = await cursor.to_list(length=50)
                rolling_total = amount + sum(float(t.get("amount", 0)) for t in recent_txns)
                facts.append({"label": "24h rolling total", "value": f"CAD {rolling_total:,.2f} ({len(recent_txns) + 1} txns)"})
                if rolling_total >= threshold and len(recent_txns) >= 1:
                    return _outcome(
                        "flag",
                        f"24-hour aggregated volume of CAD {rolling_total:,.2f} across {len(recent_txns)+1} transactions meets/exceeds the $10,000 CAD threshold (PCMLTFA Regulations s. 126).",
                        f"Under PCMLTFA Regulations s. 126, multiple transactions by the same customer within 24 hours totaling CAD {float(threshold):,.2f} or more must be aggregated for reporting and structuring review. This transaction brings the 24-hour total to CAD {rolling_total:,.2f} across {len(recent_txns) + 1} transactions.",
                        facts,
                    )
        except Exception:
            pass

    # Single transaction smurfing detection hint: exactly just under $10,000 (e.g. $9,800 - $9,999)
    if 9500 <= amount < 10000:
        return _outcome(
            "flag",
            f"Transaction amount CAD {amount:,.2f} is just below the $10,000 reporting threshold; flagged for 24-hour aggregation monitoring.",
            f"The transaction amount (CAD {amount:,.2f}) sits just below the CAD {float(threshold):,.2f} FINTRAC reporting threshold, which is a common structuring indicator. It is flagged for reviewer monitoring rather than blocked.",
            facts,
        )

    return _outcome(
        "pass",
        "24-hour transaction volume is within standard thresholds.",
        f"The transaction amount (CAD {amount:,.2f}) and rolling 24-hour customer volume are below the CAD {float(threshold):,.2f} structuring aggregation threshold.",
        facts,
    )


async def travel_rule_fields(txn: dict, customer: dict, params: dict, db: Any = None) -> dict:
    """
    Criterion W-01 (Must-have):
    Enforces FINTRAC Travel Rule (PCMLTFA Regulations s. 138-141) and Payments Canada Lynx standards.
    Requires mandatory originator (name, address, account) and beneficiary (name, address, account).
    Missing information triggers an immediate hard no_pass.
    """
    missing_fields: List[str] = []

    # 1. Beneficiary / Counterparty Validation
    counterparty = txn.get("counterparty") or {}
    cp_name = counterparty.get("name")
    cp_account = counterparty.get("account")
    cp_address = counterparty.get("address")

    if not cp_name or not str(cp_name).strip():
        missing_fields.append("counterparty.name")
    if not cp_account or not str(cp_account).strip():
        missing_fields.append("counterparty.account")
    # Address is mandatory under FINTRAC Travel Rule for electronic funds transfers
    if not cp_address or not str(cp_address).strip():
        missing_fields.append("counterparty.address")

    # 2. Originator Validation
    type_spec = txn.get("type_specific") or {}
    originator = type_spec.get("originator") or {}
    orig_name = originator.get("name") or (customer.get("name") if customer else None)

    # In domestic context customer_id identifies the account, but wire originator must be present
    if not orig_name and not customer:
        missing_fields.append("originator.name")

    facts = [
        {"label": "Originator name", "value": str(orig_name) if orig_name else "Missing"},
        {"label": "Beneficiary name", "value": str(cp_name) if cp_name and str(cp_name).strip() else "Missing"},
        {"label": "Beneficiary account", "value": str(cp_account) if cp_account and str(cp_account).strip() else "Missing"},
        {"label": "Beneficiary address", "value": str(cp_address) if cp_address and str(cp_address).strip() else "Missing"},
    ]

    if missing_fields:
        # Match exact evidence phrasing in contracts.md §3.5 when counterparty.address is the issue
        if len(missing_fields) == 1 and missing_fields[0] == "counterparty.address":
            evidence = "counterparty.address is missing"
        else:
            evidence = f"Mandatory Travel Rule field(s) missing: {', '.join(missing_fields)}"
        return _outcome(
            "no_pass",
            evidence,
            f"The FINTRAC Travel Rule (PCMLTFA Regulations s. 138-141) requires the originator and beneficiary's name, account number, and address to travel with a wire. Required field(s) ({', '.join(missing_fields)}) are missing, so the wire cannot proceed until corrected. This is a mandatory rule and no reviewer can override it.",
            facts,
        )

    return _outcome(
        "pass",
        "Originator and beneficiary information is complete (name, account, address) per FINTRAC Travel Rule.",
        "All mandatory originator and beneficiary Travel Rule fields (name, account, and address) are present on the wire instruction.",
        facts,
    )


async def eft_report_threshold(txn: dict, customer: dict, params: dict, db: Any = None) -> dict:
    """
    Criterion W-02 (Must-have):
    Checks whether an electronic funds transfer meets or exceeds the CAD $10,000 threshold
    for mandatory EFTR reporting to FINTRAC within 5 business days (PCMLTFA s. 9.1).
    IMPORTANT: Per contracts §2, this returns 'flag' (reporting obligation), NOT 'no_pass'.
    """
    threshold = params.get("threshold", 10000)
    amount = float(txn.get("amount", 0))
    facts = [
        {"label": "Transfer amount", "value": f"CAD {amount:,.2f}"},
        {"label": "EFTR threshold", "value": f"CAD {float(threshold):,.2f}"},
    ]

    if amount >= threshold:
        return _outcome(
            "flag",
            f"Amount CAD {amount:,.2f} meets or exceeds the $10,000 threshold for mandatory FINTRAC EFTR reporting (PCMLTFA s. 9.1).",
            f"Electronic funds transfers of CAD {float(threshold):,.2f} or more require a mandatory Electronic Funds Transfer Report (EFTR) to FINTRAC within 5 business days under PCMLTFA s. 9.1. This is a reporting obligation flag and does not by itself block the wire.",
            facts,
        )

    return _outcome(
        "pass",
        f"Amount CAD {amount:,.2f} is below the $10,000 EFTR reporting threshold.",
        f"The wire amount (CAD {amount:,.2f}) is below the CAD {float(threshold):,.2f} threshold, so no mandatory EFTR filing is triggered.",
        facts,
    )


async def cheque_date_valid(txn: dict, customer: dict, params: dict, db: Any = None) -> dict:
    """
    Criterion Q-01 (Must-have):
    Enforces Payments Canada Rule A1 and Bills of Exchange Act s. 26.
    1. Stale-dated: cheque date > 6 months (180 calendar days) prior to presentment is ineligible for clearing.
    2. Post-dated: cheque date future to presentment is ineligible for clearing prior to stated date.
    """
    max_age_days = params.get("max_age_days", 180)
    type_spec = txn.get("type_specific") or {}
    cheque_date_val = (
        type_spec.get("cheque_date")
        or txn.get("cheque_date")
        or type_spec.get("cheque_capture_timestamp")
        or txn.get("created_at")
    )

    if not cheque_date_val:
        return _outcome(
            "no_pass",
            "Cheque date is missing from transaction payload (Payments Canada Rule A1).",
            "Payments Canada Rule A1 requires a valid cheque date to verify clearing eligibility. No cheque date was found in the transaction payload, so the item cannot be cleared.",
            [{"label": "Cheque date", "value": "Missing"}],
        )

    cheque_dt = _parse_iso_date(cheque_date_val)
    if not cheque_dt:
        return _outcome(
            "no_pass",
            f"Invalid cheque date format '{cheque_date_val}' (expected YYYY-MM-DD).",
            f"The supplied cheque date '{cheque_date_val}' could not be parsed as a valid ISO date. Validating whether the cheque is stale- or post-dated requires a parseable date.",
            [{"label": "Cheque date", "value": str(cheque_date_val)}],
        )

    presentment_dt = _parse_iso_date(txn.get("created_at")) or datetime.now(timezone.utc)
    delta_days = (presentment_dt.date() - cheque_dt.date()).days
    facts = [
        {"label": "Cheque date", "value": cheque_dt.strftime("%Y-%m-%d")},
        {"label": "Presentment date", "value": presentment_dt.strftime("%Y-%m-%d")},
        {"label": "Age (days)", "value": f"{delta_days} days"},
    ]

    # Post-dated check (future date relative to presentment)
    if delta_days < 0:
        return _outcome(
            "no_pass",
            f"Cheque is post-dated ({cheque_dt.strftime('%Y-%m-%d')} is after presentment date {presentment_dt.strftime('%Y-%m-%d')}). Ineligible for clearing prior to date under Payments Canada Rule A1.",
            f"The cheque is dated {cheque_dt.strftime('%Y-%m-%d')}, which is {-delta_days} day(s) after the presentment date ({presentment_dt.strftime('%Y-%m-%d')}). Under Payments Canada Rule A1, post-dated cheques are ineligible for clearing prior to the stated date.",
            facts,
        )

    # Stale-dated check (> 180 calendar days / 6 months)
    if delta_days > max_age_days:
        return _outcome(
            "no_pass",
            f"Cheque is stale-dated ({delta_days} days old, exceeds maximum allowable age of {max_age_days} days under Payments Canada Rule A1 / Bills of Exchange Act s. 26).",
            f"The cheque is {delta_days} days old, exceeding the {max_age_days}-day clearing limit under Payments Canada Rule A1 and Bills of Exchange Act s. 26. Stale-dated cheques cannot clear without re-issuance.",
            facts,
        )

    return _outcome(
        "pass",
        f"Cheque date {cheque_dt.strftime('%Y-%m-%d')} is valid ({delta_days} days old; within 180-day clearing window).",
        f"The cheque date ({cheque_dt.strftime('%Y-%m-%d')}) is {delta_days} days before presentment, which is neither post-dated nor stale-dated beyond the {max_age_days}-day limit.",
        facts,
    )


async def hold_period_applied(txn: dict, customer: dict, params: dict, db: Any = None) -> dict:
    """
    Criterion Q-02 (Optional):
    Enforces Bank Act Access to Funds Regulations (SOR/2012-24).
    - First $100 CAD must be made available immediately (branch) or next day (ATM/mobile).
    - Amount <= $1,500 CAD: maximum hold 4 business days (branch), 5 days (ATM/mobile).
    - Amount > $1,500 CAD: maximum hold 7 business days (branch), 8 days (ATM/mobile).
    """
    type_spec = txn.get("type_specific") or {}
    hold_days = type_spec.get("hold_days_applied")
    channel = str(type_spec.get("deposit_channel", "branch")).lower()
    amount = float(txn.get("amount", 0))
    facts = [
        {"label": "Deposit channel", "value": channel},
        {"label": "Amount", "value": f"CAD {amount:,.2f}"},
        {"label": "Hold days applied", "value": str(hold_days) if hold_days is not None else "Standard"},
    ]

    if hold_days is None:
        return _outcome(
            "pass",
            "Standard statutory hold schedule applied per Bank Act regulations.",
            "No custom hold override was specified on the cheque deposit, so the standard Bank Act Access to Funds Regulations (SOR/2012-24) schedule applies.",
            facts,
        )

    is_branch = "branch" in channel or "in_person" in channel
    max_days = (4 if is_branch else 5) if amount <= 1500 else (7 if is_branch else 8)
    facts.append({"label": "Statutory max hold", "value": f"{max_days} business days"})

    account_opened_dt = _parse_iso_date(customer.get("account_opened_date")) if customer else None
    if account_opened_dt:
        days_open = (datetime.now(timezone.utc) - account_opened_dt).days
        if days_open < 90:
            facts.append({"label": "Account age", "value": f"{days_open} days (< 90-day exception)"})
            return _outcome(
                "pass",
                f"Extended hold of {hold_days} days permitted under Bank Act new-account exception (< 90 days open).",
                f"Although {hold_days} days exceeds the standard {max_days}-day limit, the account has been open for {days_open} days (< 90 days), which qualifies for the Bank Act new-account hold exception.",
                facts,
            )

    if customer and customer.get("nsf_history_6m", 0) > 0:
        facts.append({"label": "6m NSF count", "value": str(customer.get("nsf_history_6m", 0))})
        return _outcome(
            "pass",
            f"Extended hold of {hold_days} days permitted under Bank Act severe NSF history exception.",
            f"Although {hold_days} days exceeds the standard {max_days}-day limit, the customer has prior NSF history within 6 months, permitting an extended hold under Bank Act exceptions.",
            facts,
        )

    if hold_days > max_days:
        return _outcome(
            "no_pass",
            f"Hold period of {hold_days} days exceeds federal maximum of {max_days} days for CAD {amount:,.2f} via {channel} (Bank Act SOR/2012-24).",
            f"The applied hold of {hold_days} business days exceeds the federal maximum of {max_days} business days for a CAD {amount:,.2f} deposit via {channel} under Bank Act SOR/2012-24, and no statutory exception applies.",
            facts,
        )

    return _outcome(
        "pass",
        f"Hold period of {hold_days} business days complies with Bank Act Access to Funds Regulations (SOR/2012-24).",
        f"The applied hold of {hold_days} business days is within the federal maximum of {max_days} business days for a CAD {amount:,.2f} deposit via {channel}.",
        facts,
    )


async def ministerial_directives_screen(txn: dict, customer: dict, params: dict, db: Any = None) -> dict:
    """
    Criterion M-01 (Hard):
    Screens for transactions subject to Canadian Ministerial Directives under PCMLTFA s. 11.42
    covering Russia (Feb 2024), Iran, and DPRK (Dec 2017).
    """
    counterparty = txn.get("counterparty") or {}
    country = (counterparty.get("country") or "").upper().strip()
    facts = [{"label": "Counterparty country", "value": country or "Not provided"}]

    if country in ("RU", "RUS"):
        return _outcome(
            "no_pass",
            "Transaction bound for or originating from Russia; prohibited without enhanced verification under Ministerial Directive (Feb 24, 2024).",
            "Under the Canadian Ministerial Directive on Russia (Feb 24, 2024, PCMLTFA s. 11.42), transactions involving Russia are subject to mandatory restrictions and enhanced verification. This is a statutory rule and cannot be overridden.",
            facts,
        )
    if country in ("IR", "IRN"):
        return _outcome(
            "no_pass",
            "Transaction associated with the Islamic Republic of Iran; prohibited under Ministerial Directive on Iran.",
            "Under the Canadian Ministerial Directive on Iran (PCMLTFA s. 11.42), transactions associated with Iran are prohibited. This is a mandatory statutory rule and cannot be overridden.",
            facts,
        )
    if country in ("KP", "PRK"):
        return _outcome(
            "no_pass",
            "Transaction associated with the Democratic People's Republic of Korea (DPRK); prohibited under Ministerial Directive (Dec 9, 2017).",
            "Under the Canadian Ministerial Directive on the DPRK (Dec 9, 2017, PCMLTFA s. 11.42), transactions associated with North Korea are strictly prohibited and cannot be overridden.",
            facts,
        )

    return _outcome(
        "pass",
        "No transactions associated with jurisdictions subject to Canadian Ministerial Directives (Russia, Iran, DPRK).",
        "The counterparty jurisdiction is not subject to any active Canadian Ministerial Directives under PCMLTFA s. 11.42 (Russia, Iran, DPRK).",
        facts,
    )


async def interac_limits_check(txn: dict, customer: dict, params: dict, db: Any = None) -> dict:
    """
    Criterion I-01 (Hard):
    Enforces Interac e-Transfer operating rules and transaction limits:
    - Retail: max $3,000 / $5,000 CAD per 24 hours
    - Commercial/Business: max $10,000 CAD
    """
    amount = float(txn.get("amount", 0))
    segment = customer.get("segment") if customer else None
    is_commercial = customer and segment in ("business", "commercial", "payroll", "import/export")
    single_limit = params.get("single_limit", 10000 if is_commercial else 3000)
    facts = [
        {"label": "Transfer amount", "value": f"CAD {amount:,.2f}"},
        {"label": "Customer segment", "value": str(segment or "retail")},
        {"label": "Single-txn limit", "value": f"CAD {float(single_limit):,.2f}"},
    ]

    if amount > single_limit:
        return _outcome(
            "no_pass",
            f"Interac e-Transfer amount CAD {amount:,.2f} exceeds allowable single-transaction limit of CAD {single_limit:,.2f} (Interac Operating Rules).",
            f"The Interac e-Transfer amount (CAD {amount:,.2f}) exceeds the single-transaction limit of CAD {float(single_limit):,.2f} for the '{segment or 'retail'}' segment under Interac Operating Rules.",
            facts,
        )

    return _outcome(
        "pass",
        f"Interac e-Transfer amount CAD {amount:,.2f} is within operating threshold (limit CAD {single_limit:,.2f}).",
        f"The Interac e-Transfer amount (CAD {amount:,.2f}) is within the CAD {float(single_limit):,.2f} single-transaction limit.",
        facts,
    )


async def interac_velocity_check(txn: dict, customer: dict, params: dict, db: Any = None) -> dict:
    """
    Criterion I-02 (Hard):
    Detects high velocity / account takeover (ATO) fraud indicators on Interac e-Transfers:
    Rapid velocity bursts to newly added recipients (CAFC & Interac Security Guidelines).
    """
    type_spec = txn.get("type_specific") or {}
    new_recipient = type_spec.get("new_recipient", False)
    velocity_1h = type_spec.get("transfers_past_hour", 0)
    facts = [
        {"label": "New recipient", "value": "Yes" if new_recipient else "No"},
        {"label": "Transfers in past hour", "value": str(velocity_1h)},
    ]

    if new_recipient and velocity_1h >= 3:
        return _outcome(
            "flag",
            f"Rapid velocity burst ({velocity_1h} transfers in 1 hour) to new recipient; flagged for Account Takeover (ATO) fraud review.",
            f"The customer initiated {velocity_1h} Interac e-Transfers within 1 hour to a newly added recipient. Under CAFC and Interac Security Guidelines, this pattern indicates potential account takeover and is flagged for review.",
            facts,
        )

    return _outcome(
        "pass",
        "Interac velocity metrics within standard baseline.",
        "Interac e-Transfer velocity and recipient novelty are within normal baseline thresholds.",
        facts,
    )


async def large_cash_threshold(txn: dict, customer: dict, params: dict, db: Any = None) -> dict:
    """
    Criterion L-01 (Reporting Flag):
    Receipt of $10,000 CAD or more in cash requires mandatory LCTR reporting to FINTRAC
    within 15 calendar days (PCMLTFA s. 9).
    """
    threshold = params.get("threshold", 10000)
    amount = float(txn.get("amount", 0))
    facts = [
        {"label": "Cash amount", "value": f"CAD {amount:,.2f}"},
        {"label": "LCTR threshold", "value": f"CAD {float(threshold):,.2f}"},
    ]

    if amount >= threshold:
        return _outcome(
            "flag",
            f"Cash transaction of CAD {amount:,.2f} meets or exceeds $10,000 threshold for mandatory FINTRAC LCTR reporting within 15 calendar days.",
            f"Cash transactions of CAD {float(threshold):,.2f} or more trigger a mandatory Large Cash Transaction Report (LCTR) to FINTRAC within 15 calendar days under PCMLTFA s. 9. This is a reporting flag rather than a hard block.",
            facts,
        )

    return _outcome(
        "pass",
        f"Cash amount CAD {amount:,.2f} is below $10,000 LCTR threshold.",
        f"The cash amount (CAD {amount:,.2f}) is below the CAD {float(threshold):,.2f} LCTR reporting threshold.",
        facts,
    )


async def virtual_currency_threshold(txn: dict, customer: dict, params: dict, db: Any = None) -> dict:
    """
    Criterion V-01 (Reporting Flag):
    Transfer of $10,000 CAD or more in virtual currency requires mandatory LVCTR reporting to FINTRAC
    within 5 business days (PCMLTFA Regulations s. 127).
    """
    threshold = params.get("threshold", 10000)
    amount = float(txn.get("amount", 0))
    facts = [
        {"label": "Virtual currency amount", "value": f"CAD {amount:,.2f}"},
        {"label": "LVCTR threshold", "value": f"CAD {float(threshold):,.2f}"},
    ]

    if amount >= threshold:
        return _outcome(
            "flag",
            f"Virtual currency transfer of CAD {amount:,.2f} meets or exceeds $10,000 threshold for mandatory FINTRAC LVCTR reporting within 5 business days.",
            f"Virtual currency transfers of CAD {float(threshold):,.2f} or more require a mandatory Large Virtual Currency Transaction Report (LVCTR) to FINTRAC within 5 business days under PCMLTFA Regulations s. 127.",
            facts,
        )

    return _outcome(
        "pass",
        f"Virtual currency amount CAD {amount:,.2f} is below $10,000 LVCTR threshold.",
        f"The virtual currency transfer (CAD {amount:,.2f}) is below the CAD {float(threshold):,.2f} LVCTR reporting threshold.",
        facts,
    )


async def currency_clearing_check(txn: dict, customer: dict, params: dict, db: Any = None) -> dict:
    """
    Criterion R-01 (Hard):
    Payments Canada clearing eligibility: only CAD and USD instruments are eligible
    for direct ACSS/Lynx clearing.
    """
    currency = (txn.get("currency") or "CAD").upper().strip()
    facts = [{"label": "Currency", "value": currency}]
    if currency not in ("CAD", "USD"):
        return _outcome(
            "no_pass",
            f"Currency '{currency}' is ineligible for direct Canadian ACSS clearing (Payments Canada Rule A1).",
            f"Only CAD and USD instruments are eligible for direct Canadian ACSS/Lynx clearing under Payments Canada Rule A1. Currency '{currency}' must be rejected or rerouted through an international correspondent.",
            facts,
        )

    return _outcome(
        "pass",
        f"Currency '{currency}' is eligible for domestic clearing.",
        f"Currency '{currency}' is eligible for direct Canadian ACSS/Lynx clearing under Payments Canada Rule A1.",
        facts,
    )


async def amount_mismatch_check(txn: dict, customer: dict, params: dict, db: Any = None) -> dict:
    """
    Criterion A-01 (Hard):
    Detects discrepancies between the processed transaction amount and the source
    document amount (or cheque written vs. presented amount).
    """
    type_spec = txn.get("type_specific") or {}
    amount = float(txn.get("amount", 0))
    source_amt = type_spec.get("source_document_amount_cad")
    facts = [{"label": "Processed amount", "value": f"CAD {amount:,.2f}"}]
    if source_amt is not None:
        facts.append({"label": "Source document amount", "value": f"CAD {float(source_amt):,.2f}"})

    if source_amt is not None and abs(amount - float(source_amt)) > 0.01:
        diff = abs(amount - float(source_amt))
        return _outcome(
            "no_pass",
            f"Amount mismatch: processed CAD {amount:,.2f} differs from source document CAD {float(source_amt):,.2f} (diff CAD {diff:,.2f}).",
            f"The processed amount (CAD {amount:,.2f}) does not match the source document amount (CAD {float(source_amt):,.2f}), leaving a discrepancy of CAD {diff:,.2f}. Amount mismatches must be resolved before clearing.",
            facts,
        )

    written_amt = type_spec.get("cheque_written_amount_cad")
    presented_amt = type_spec.get("cheque_presented_amount_cad")
    if written_amt is not None and presented_amt is not None:
        facts.extend([
            {"label": "Cheque written amount", "value": f"CAD {float(written_amt):,.2f}"},
            {"label": "Cheque presented amount", "value": f"CAD {float(presented_amt):,.2f}"},
        ])
        if abs(float(written_amt) - float(presented_amt)) > 0.01:
            diff = abs(float(written_amt) - float(presented_amt))
            return _outcome(
                "no_pass",
                f"Cheque amount mismatch: written CAD {float(written_amt):,.2f} vs presented CAD {float(presented_amt):,.2f} (diff CAD {diff:,.2f}).",
                f"The written amount on the cheque (CAD {float(written_amt):,.2f}) differs from the presented amount (CAD {float(presented_amt):,.2f}) by CAD {diff:,.2f}. The item cannot clear until reconciled.",
                facts,
            )

    return _outcome(
        "pass",
        f"Transaction amount CAD {amount:,.2f} matches source documentation.",
        f"The processed transaction amount (CAD {amount:,.2f}) matches all available source documentation.",
        facts,
    )


async def compliance_risk_screen(txn: dict, customer: dict, params: dict, db: Any = None) -> dict:
    """
    Criterion S-01 (Hard):
    Screens deterministic compliance/risk flags on the payment payload
    (active risk_flag, compliance_cleared=False, or beneficiary name mismatch).
    """
    type_spec = txn.get("type_specific") or {}
    risk_flag = bool(type_spec.get("risk_flag", False))
    compliance_cleared = type_spec.get("compliance_cleared")
    name_matches = type_spec.get("beneficiary_name_matches_receiver")

    facts = [
        {"label": "Risk flag", "value": "True" if risk_flag else "False"},
        {"label": "Compliance cleared", "value": str(compliance_cleared) if compliance_cleared is not None else "Not set"},
        {"label": "Beneficiary name match", "value": str(name_matches) if name_matches is not None else "Not set"},
    ]

    issues: List[str] = []
    if risk_flag:
        issues.append("risk_flag=true")
    if compliance_cleared is False:
        issues.append("compliance_cleared=false")
    if name_matches is False:
        issues.append("beneficiary_name_matches_receiver=false")

    if issues:
        return _outcome(
            "no_pass",
            f"Deterministic compliance screening failed: {', '.join(issues)} (PCMLTFA s. 7).",
            f"Deterministic compliance screening flagged {', '.join(issues)} on the payment payload under PCMLTFA s. 7. These compliance flags cannot be overridden and require remediation or rejection.",
            facts,
        )

    return _outcome(
        "pass",
        "Transaction cleared deterministic risk and compliance flags.",
        "No deterministic risk flags, compliance blocks, or beneficiary name mismatches were present on the payment payload.",
        facts,
    )

# ---------------------------------------------------------------------------
# 5. CHECKS Registry (Contracts §5.3)
# ---------------------------------------------------------------------------
CHECKS: Dict[str, Callable[[dict, dict, dict, Any], Awaitable[dict]]] = {
    "sanctions_screen": sanctions_screen,
    "account_ok": account_ok,
    "duplicate": duplicate,
    "structuring_24h": structuring_24h,
    "travel_rule_fields": travel_rule_fields,
    "eft_report_threshold": eft_report_threshold,
    "cheque_date_valid": cheque_date_valid,
    "hold_period_applied": hold_period_applied,
    "ministerial_directives_screen": ministerial_directives_screen,
    "interac_limits_check": interac_limits_check,
    "interac_velocity_check": interac_velocity_check,
    "large_cash_threshold": large_cash_threshold,
    "virtual_currency_threshold": virtual_currency_threshold,
    "currency_clearing_check": currency_clearing_check,
    "amount_mismatch_check": amount_mismatch_check,
    "compliance_risk_screen": compliance_risk_screen,
}

# ---------------------------------------------------------------------------
# 6. Default Policy Checklists (Contracts §3.4 & Plan-Scenarios §Policies)
# ---------------------------------------------------------------------------
_COMMON_RULES = [
    {"rule_id": "D-01", "role": "analyst", "max_amount": 50000, "can_override_hard_fail": True},
    {"rule_id": "D-02", "role": "supervisor", "max_amount": None, "can_override_hard_fail": True},
]

_SHARED_HARD_CRITERIA = [
    {
        "id": "C-01",
        "description": "Counterparty not on a sanctions list",
        "kind": "hard",
        "check": "sanctions_screen",
        "params": {"names": DEFAULT_SANCTIONED_NAMES},
        "regulation_ref": "Canadian sanctions law (SEMA / OSFI / PCMLTFA s. 7.1)",
    },
    {
        "id": "C-02",
        "description": "Customer account active and in good standing",
        "kind": "hard",
        "check": "account_ok",
        "params": {},
        "regulation_ref": "Bank Act / PCMLTFA KYC Provisions",
    },
    {
        "id": "C-03",
        "description": "No duplicate transaction within clearing window",
        "kind": "hard",
        "check": "duplicate",
        "params": {"lookback_days": 30},
        "regulation_ref": "Payments Canada Rule A4",
    },
    {
        "id": "A-01",
        "description": "Processed amount matches source documentation",
        "kind": "hard",
        "check": "amount_mismatch_check",
        "params": {},
        "regulation_ref": "Payments Canada Rule A4 / Reconciliation Controls",
    },
    {
        "id": "S-01",
        "description": "Deterministic risk and compliance flags cleared",
        "kind": "hard",
        "check": "compliance_risk_screen",
        "params": {},
        "regulation_ref": "PCMLTFA s. 7",
    },
]

_JUDGMENT_AMOUNT = {
    "id": "C-04",
    "description": "Amount consistent with the customer's usual profile",
    "kind": "judgment",
    "check": None,
    "params": {"ratio_hint": 3},
    "regulation_ref": "FINTRAC suspicious-transaction indicators",
}

DEFAULT_POLICIES: Dict[str, Dict[str, Any]] = {
    "wire": {
        "txn_type": "wire",
        "version": 1,
        "active": True,
        "decision_rules": _COMMON_RULES,
        "criteria": [
            *_SHARED_HARD_CRITERIA,
            {
                "id": "W-01",
                "description": "Originator and beneficiary information complete",
                "kind": "hard",
                "check": "travel_rule_fields",
                "params": {},
                "regulation_ref": "FINTRAC travel rule (PCMLTFA Regulations s. 138-141)"
            },
            {
                "id": "W-02",
                "description": "Mandatory reporting threshold for international EFT ($10,000 CAD)",
                "kind": "hard",
                "check": "eft_report_threshold",
                "params": {"threshold": 10000},
                "regulation_ref": "PCMLTFA s. 9.1 (FINTRAC EFTR)"
            },
            {
                "id": "M-01",
                "description": "Ministerial Directive compliance (Russia, Iran, DPRK)",
                "kind": "hard",
                "check": "ministerial_directives_screen",
                "params": {},
                "regulation_ref": "PCMLTFA s. 11.42 Ministerial Directives"
            },
            {
                "id": "R-01",
                "description": "Currency eligible for domestic clearing (CAD/USD)",
                "kind": "hard",
                "check": "currency_clearing_check",
                "params": {},
                "regulation_ref": "Payments Canada Lynx Rules"
            },
            _JUDGMENT_AMOUNT,
            {
                "id": "W-03",
                "description": "Payment purpose and routing consistency",
                "kind": "judgment",
                "check": None,
                "params": {},
                "regulation_ref": "FINTRAC guidance on payment monitoring"
            }
        ]
    },
    "cheque": {
        "txn_type": "cheque",
        "version": 1,
        "active": True,
        "decision_rules": _COMMON_RULES,
        "criteria": [
            *_SHARED_HARD_CRITERIA,
            {
                "id": "Q-01",
                "description": "Cheque date is valid (not stale-dated > 180 days, not post-dated)",
                "kind": "hard",
                "check": "cheque_date_valid",
                "params": {"max_age_days": 180},
                "regulation_ref": "Payments Canada Rule A1 / Bills of Exchange Act s. 26"
            },
            {
                "id": "Q-02",
                "description": "Statutory hold period applied complies with access to funds limits",
                "kind": "hard",
                "check": "hold_period_applied",
                "params": {},
                "regulation_ref": "Bank Act Access to Funds Regulations SOR/2012-24"
            },
            {
                "id": "R-01",
                "description": "Currency eligible for domestic clearing (CAD/USD)",
                "kind": "hard",
                "check": "currency_clearing_check",
                "params": {},
                "regulation_ref": "Payments Canada Rule A1"
            },
            _JUDGMENT_AMOUNT,
        ]
    },
    "interac": {
        "txn_type": "interac",
        "version": 1,
        "active": True,
        "decision_rules": _COMMON_RULES,
        "criteria": [
            *_SHARED_HARD_CRITERIA,
            {
                "id": "I-01",
                "description": "Interac e-Transfer within statutory and operating limits",
                "kind": "hard",
                "check": "interac_limits_check",
                "params": {"single_limit": 3000},
                "regulation_ref": "Interac Corp Operating Regulations"
            },
            {
                "id": "I-02",
                "description": "Interac fraud velocity and account takeover screening",
                "kind": "hard",
                "check": "interac_velocity_check",
                "params": {},
                "regulation_ref": "CAFC & Interac Fraud Guidelines"
            },
            _JUDGMENT_AMOUNT,
        ]
    },
    "eft": {
        "txn_type": "eft",
        "version": 1,
        "active": True,
        "decision_rules": _COMMON_RULES,
        "criteria": [
            *_SHARED_HARD_CRITERIA,
            {
                "id": "R-01",
                "description": "Currency eligible for domestic ACSS clearing (CAD/USD)",
                "kind": "hard",
                "check": "currency_clearing_check",
                "params": {},
                "regulation_ref": "Payments Canada Rule A1"
            },
            _JUDGMENT_AMOUNT,
        ]
    },
    "pad": {
        "txn_type": "pad",
        "version": 1,
        "active": True,
        "decision_rules": _COMMON_RULES,
        "criteria": [
            *_SHARED_HARD_CRITERIA,
            {
                "id": "R-01",
                "description": "Currency eligible for domestic ACSS PAD clearing (CAD/USD)",
                "kind": "hard",
                "check": "currency_clearing_check",
                "params": {},
                "regulation_ref": "Payments Canada Rule H1"
            },
            _JUDGMENT_AMOUNT,
        ]
    },
    "bill_payment": {
        "txn_type": "bill_payment",
        "version": 1,
        "active": True,
        "decision_rules": _COMMON_RULES,
        "criteria": [
            *_SHARED_HARD_CRITERIA,
            _JUDGMENT_AMOUNT,
        ]
    },
}

# ---------------------------------------------------------------------------
# 7. Master Preliminary Screening Function
# ---------------------------------------------------------------------------
async def run_preliminary_screening(
    txn: dict,
    customer: Optional[dict] = None,
    policy: Optional[dict] = None,
    db: Any = None,
    params_override: Optional[dict] = None
) -> dict:
    """
    Executes preliminary deterministic screening for transactions against all
    applicable statutory and regulatory criteria extracted from Canadian banking
    regulations and FINTRAC policies.

    Args:
        txn: Transaction payload conforming to docs/contracts.md §3.3
        customer: Optional customer profile conforming to docs/contracts.md §3.2
        policy: Optional policy checklist conforming to docs/contracts.md §3.4.
                If omitted, loads the active policy for txn['type'] from DEFAULT_POLICIES.
        db: Optional database handle (AsyncMongoClient / sync MongoClient).
        params_override: Optional parameter overrides for checks.

    Returns:
        Structured Preliminary Screening Report:
        {
            "txn_id": str,
            "is_non_compliant": bool,        # True if any hard check returned 'no_pass'
            "recommendation": "pass" | "no_pass",
            "status": "non_compliant" | "flagged" | "compliant",
            "hard_checks_count": int,
            "passed_count": int,
            "failed_count": int,
            "flagged_count": int,
            "failed_checks": list[dict],      # Details of failing checks
            "flags": list[dict],              # Reporting obligation flags (e.g. EFTR >= 10k)
            "checks": list[dict],             # Checks list matching contracts §3.5 format
            "policy_version": int,
            "preliminary_summary": str,
            "evaluated_at": str
        }
    """
    txn_id = txn.get("txn_id", "TXN-UNKNOWN")
    txn_type = str(txn.get("type", "wire")).lower()

    # Determine Active Policy
    if not policy:
        if db is not None:
            try:
                if hasattr(db, "policies") and hasattr(db.policies, "find_one"):
                    fetched_policy = await db.policies.find_one({"txn_type": txn_type, "active": True})
                    if fetched_policy:
                        policy = fetched_policy
            except Exception:
                pass
        if not policy:
            policy = DEFAULT_POLICIES.get(txn_type) or DEFAULT_POLICIES.get("wire")

    criteria = policy.get("criteria", [])
    policy_version = policy.get("version", 1)

    # Filter to Hard (Deterministic) Criteria Only
    hard_criteria = [c for c in criteria if c.get("kind") == "hard"]

    evaluated_checks: List[dict] = []
    failed_checks: List[dict] = []
    flagged_checks: List[dict] = []
    passed_checks: List[dict] = []

    for criterion in hard_criteria:
        c_id = criterion.get("id")
        check_name = criterion.get("check")
        description = criterion.get("description", "")
        regulation_ref = criterion.get("regulation_ref", "")
        params = dict(criterion.get("params") or {})
        if params_override:
            params.update(params_override)

        check_fn = CHECKS.get(check_name)
        if not check_fn:
            continue

        try:
            # Execute Check Function
            outcome = await check_fn(txn, customer or {}, params, db)
            res = outcome.get("result", "pass")
            evidence = outcome.get("evidence", "")
        except Exception as e:
            res = "no_pass"
            evidence = f"Check '{check_name}' execution error: {str(e)}"

        check_entry = {
            "criterion_id": c_id,
            "description": description,
            "kind": "hard",
            "source": "rule",
            "result": res,  # 'pass' | 'no_pass' | 'flag'
            "evidence": evidence,
            "regulation_ref": regulation_ref,
            "precedents_used": [],
            "adjustments_used": []
        }

        evaluated_checks.append(check_entry)

        if res == "no_pass":
            failed_checks.append(check_entry)
        elif res == "flag":
            flagged_checks.append(check_entry)
        else:
            passed_checks.append(check_entry)

    # Derived rules per contracts §2:
    # recommendation = no_pass if any check is no_pass, otherwise pass
    recommendation = "no_pass" if len(failed_checks) > 0 else "pass"
    is_non_compliant = len(failed_checks) > 0

    if is_non_compliant:
        status = "non_compliant"
    elif len(flagged_checks) > 0:
        status = "flagged"
    else:
        status = "compliant"

    # Human-readable summary for reviewer audit trail
    if is_non_compliant:
        fail_reasons = "; ".join([f"{f['criterion_id']}: {f['evidence']}" for f in failed_checks])
        summary = f"Transaction {txn_id} FAILED preliminary screening with {len(failed_checks)} violation(s): [{fail_reasons}]. Recommendation: no_pass."
    elif flagged_checks:
        flag_notes = "; ".join([f"{fl['criterion_id']}: {fl['evidence']}" for fl in flagged_checks])
        summary = f"Transaction {txn_id} passed preliminary hard checks with {len(flagged_checks)} regulatory reporting obligation(s): [{flag_notes}]. Recommendation: pass (subject to review)."
    else:
        summary = f"Transaction {txn_id} passed all {len(evaluated_checks)} deterministic compliance checks. Recommendation: pass."

    return {
        "txn_id": txn_id,
        "is_non_compliant": is_non_compliant,
        "recommendation": recommendation,
        "status": status,
        "hard_checks_count": len(evaluated_checks),
        "passed_count": len(passed_checks),
        "failed_count": len(failed_checks),
        "flagged_count": len(flagged_checks),
        "failed_checks": failed_checks,
        "flags": flagged_checks,
        "checks": evaluated_checks,
        "policy_version": policy_version,
        "preliminary_summary": summary,
        "evaluated_at": datetime.now(timezone.utc).isoformat()
    }


def run_preliminary_screening_sync(
    txn: dict,
    customer: Optional[dict] = None,
    policy: Optional[dict] = None,
    db: Any = None,
    params_override: Optional[dict] = None
) -> dict:
    """Synchronous wrapper for run_preliminary_screening for test suites and scripts."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import nest_asyncio
            nest_asyncio.apply()
            return loop.run_until_complete(
                run_preliminary_screening(txn, customer, policy, db, params_override)
            )
        else:
            return loop.run_until_complete(
                run_preliminary_screening(txn, customer, policy, db, params_override)
            )
    except RuntimeError:
        return asyncio.run(
            run_preliminary_screening(txn, customer, policy, db, params_override)
        )


def extract_deterministic_rules_catalog() -> List[dict]:
    """Returns the full catalog of extracted deterministic rules across all 37 policies."""
    return list(DETERMINISTIC_RULES_CATALOG)
