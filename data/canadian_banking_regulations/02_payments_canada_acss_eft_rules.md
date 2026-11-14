# Payments Canada ACSS Rules for Electronic Funds Transfers (Rule E1 & E2)

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
