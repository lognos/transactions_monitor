# Payments Canada Rule A1: Clearing Eligibility, Stale-Dating & Post-Dating

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
