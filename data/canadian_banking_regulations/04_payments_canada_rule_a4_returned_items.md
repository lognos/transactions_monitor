# Payments Canada Rule A4: Returned and Redirected Items (Duplicate Cheque Recourse)

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
