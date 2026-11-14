# Bank Act: Access to Funds Regulations (SOR/2012-24) Maximum Cheque Hold Limits

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
