# Payments Canada Lynx Rules & Standards for Electronic Wire Clearing

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
