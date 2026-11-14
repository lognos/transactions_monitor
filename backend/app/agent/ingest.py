"""CSV and streaming transaction ingestion normalizer.

Converts raw rows from `data/AuditFlow_All_Transactions_Consolidated.csv` (or future
polling / WebSocket payloads with the same schema) into `customers` and `transactions`
documents conforming to `docs/contracts.md §3.2` and `§3.3`.

Test-only ground-truth columns (`test_only_*`, `case_*`) are intentionally stripped so
deterministic checks and the LLM agent never see expected answers.
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

_METHOD_MAP: Dict[str, str] = {
    "WIRE": "wire",
    "CHEQUE": "cheque",
    "EFT": "eft",
    "INTERAC_E_TRANSFER": "interac",
    "PAD": "pad",
    "BILL_PAYMENT": "bill_payment",
}


def _parse_bool(val: Any) -> Optional[bool]:
    if isinstance(val, bool):
        return val
    if val is None:
        return None
    s = str(val).strip().lower()
    if s in ("true", "1", "yes"):
        return True
    if s in ("false", "0", "no"):
        return False
    return None


def _parse_float(val: Any) -> Optional[float]:
    if val is None or str(val).strip() == "":
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def _clean_str(val: Any) -> Optional[str]:
    if val is None:
        return None
    s = str(val).strip()
    return s if s else None


def normalize_csv_row(row: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Normalize a single consolidated CSV / stream row into `(customer_doc, txn_doc)`."""
    raw_method = str(row.get("payment_method") or "WIRE").strip().upper()
    txn_type = _METHOD_MAP.get(raw_method, raw_method.lower())

    txn_id = _clean_str(row.get("transaction_id")) or ""
    customer_id = _clean_str(row.get("source_account_id")) or f"CUS-{txn_id}"
    amount = _parse_float(row.get("amount_cad")) or 0.0
    currency = (_clean_str(row.get("currency")) or "CAD").upper()

    sender_name = _clean_str(row.get("sender_customer_name")) or _clean_str(row.get("payer_name")) or "Unknown"
    sender_type = (_clean_str(row.get("sender_account_holder_type")) or "PERSONAL").lower()
    sender_status = (_clean_str(row.get("sender_account_status")) or "ACTIVE").lower()
    sender_balance = _parse_float(row.get("sender_available_balance_cad"))
    sender_province = _clean_str(row.get("sender_province")) or _clean_str(row.get("province"))

    customer_doc: Dict[str, Any] = {
        "customer_id": customer_id,
        "name": sender_name,
        "segment": "business" if sender_type == "business" else "retail",
        "risk_rating": "high" if _parse_bool(row.get("risk_flag")) else "low",
        "typical_amount": amount,
        "country": "CA",
        "province": sender_province,
        "account_status": "open" if sender_status == "active" else sender_status,
        "balance": sender_balance if sender_balance is not None else 0.0,
        "account_number": _clean_str(row.get("sender_account_number_demo")),
        "account_opened_date": _clean_str(row.get("sender_account_opened_date")),
        "kyc_status": _clean_str(row.get("sender_kyc_status")),
    }

    receiver_name = _clean_str(row.get("receiver_customer_name")) or _clean_str(row.get("payee_name"))
    receiver_acct = _clean_str(row.get("receiver_account_number_demo")) or _clean_str(row.get("destination_account_id"))
    receiver_province = _clean_str(row.get("receiver_province")) or _clean_str(row.get("province"))
    receiver_address = f"{receiver_province}, CA" if receiver_province else None
    sender_address = f"{sender_province}, CA" if sender_province else None

    posting_raw = (_clean_str(row.get("posting_status")) or "PENDING").upper()
    status_map = {"PENDING": "pending", "POSTED": "passed", "RETURNED": "rejected"}

    type_specific: Dict[str, Any] = {
        "payment_method": raw_method,
        "direction": _clean_str(row.get("direction")),
        "payment_channel": _clean_str(row.get("payment_channel")),
        "payment_reference": _clean_str(row.get("payment_reference")),
        "posting_status": posting_raw,
        "source_document_amount_cad": _parse_float(row.get("source_document_amount_cad")),
        "risk_flag": bool(_parse_bool(row.get("risk_flag"))),
        "compliance_cleared": _parse_bool(row.get("compliance_cleared")),
        "destination_is_new": bool(_parse_bool(row.get("destination_is_new"))),
        "new_beneficiary": bool(_parse_bool(row.get("destination_is_new"))),
        "return_reason_code": _clean_str(row.get("return_reason_code")),
        "original_transaction_id": _clean_str(row.get("original_transaction_id")),
        "sender_account_status": (_clean_str(row.get("sender_account_status")) or "ACTIVE").upper(),
        "receiver_account_status": (_clean_str(row.get("receiver_account_status")) or "ACTIVE").upper(),
        "sender_kyc_status": _clean_str(row.get("sender_kyc_status")),
        "receiver_kyc_status": _clean_str(row.get("receiver_kyc_status")),
        "beneficiary_name_matches_receiver": _parse_bool(row.get("beneficiary_name_matches_receiver")),
        "originator": {
            "name": sender_name,
            "account": _clean_str(row.get("sender_account_number_demo")) or customer_id,
            "address": sender_address,
        },
        "international": False,
    }

    if txn_type == "cheque" or _parse_bool(row.get("has_cheque_item")):
        capture_ts = _clean_str(row.get("cheque_capture_timestamp")) or _clean_str(row.get("transaction_datetime"))
        type_specific.update(
            {
                "cheque_number": _clean_str(row.get("cheque_number")) or _clean_str(row.get("cheque_cheque_number")),
                "image_hash": _clean_str(row.get("cheque_image_hash")) or _clean_str(row.get("cheque_cheque_image_hash_demo")),
                "cheque_date": capture_ts[:10] if capture_ts else None,
                "cheque_capture_timestamp": capture_ts,
                "deposit_channel": (_clean_str(row.get("cheque_capture_channel")) or "branch").lower(),
                "cheque_written_amount_cad": _parse_float(row.get("cheque_written_amount_cad")),
                "cheque_presented_amount_cad": _parse_float(row.get("cheque_presented_amount_cad")),
                "cheque_signature_verified": _clean_str(row.get("cheque_signature_verified")),
                "cheque_account_funds_checked": _clean_str(row.get("cheque_account_funds_checked")),
                "cheque_image_quality_status": _clean_str(row.get("cheque_image_quality_status")),
            }
        )

    txn_doc: Dict[str, Any] = {
        "txn_id": txn_id,
        "type": txn_type,
        "amount": amount,
        "currency": currency,
        "customer_id": customer_id,
        "counterparty": {
            "name": receiver_name,
            "account": receiver_acct,
            "address": receiver_address,
            "country": "CA",
            "institution": _clean_str(row.get("destination_institution")),
        },
        "memo": _clean_str(row.get("description")) or "",
        "created_at": _clean_str(row.get("transaction_datetime")) or "",
        "status": status_map.get(posting_raw, "pending"),
        "type_specific": type_specific,
    }

    return customer_doc, txn_doc


def load_csv_transactions(
    csv_path: str | Path,
    *,
    limit: Optional[int] = None,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Read and normalize rows from a consolidated CSV file."""
    path = Path(csv_path)
    customers_by_id: Dict[str, Dict[str, Any]] = {}
    txns: List[Dict[str, Any]] = []

    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for idx, row in enumerate(reader):
            if limit is not None and idx >= limit:
                break
            cust, txn = normalize_csv_row(row)
            customers_by_id.setdefault(cust["customer_id"], cust)
            txns.append(txn)

    return list(customers_by_id.values()), txns
