# Project Case: Auditable Payment Exception Resolution Agent

> **Problem Statement Alignment:** **Problem 1 – Agents You Can Audit**  
> *"Build an agent using MongoDB Atlas as the identity, policy and audit layer that takes real actions across systems, where every action is tied to an identity, checked against policy before it runs, and recorded so a reviewer can reconstruct it afterward."*

---

## 1. Executive Summary & Business Idea

Financial operations teams handle high volumes of payment exceptions (e.g., sanctioned accounts, mismatched routing numbers, suspicious velocity, or over-limit transfers). 

This project implements an **autonomous AI operations agent that investigates and resolves payment exceptions**. Rather than granting unconstrained execution permissions, **every single tool call is intercepted by a MongoDB Atlas governance layer** that enforces:
1. **Identity & Delegation:** The agent acts explicitly on behalf of an authenticated human operator with defined roles and delegations (`Agent X` acts for `User Y`).
2. **Pre-Execution Policy Gates:** Deterministic policies evaluated *before* execution (e.g., *"Agents may hold payments under \$10K but not release them"*, *"Releases over \$50K require two approvers"*, *"No access to PII fields for VIP accounts"*).
3. **Immutable, Tamper-Evident Audit:** An append-only ledger capturing intent, policy decisions, tool inputs/outputs, reasoning, and cryptographic hash chains.

---

## 2. MongoDB Atlas Architecture & Schema Design

```mermaid
flowchart TD
    User([Human Operator]) -->|Delegates Task| Agent([LLM Agent])
    Agent -->|1. Proposes Tool Call| Gate[Atlas Policy Interceptor]
    
    subgraph MongoDB_Atlas [MongoDB Atlas Governance Layer]
        Identities[(identities)]
        Policies[(policies)]
        Payments[(payments)]
        Audit[(audit_events\nHash-Chained & Immutable)]
        ChangeStreams[Atlas Change Streams]
    end

    Gate -->|Verify Authority| Identities
    Gate -->|Evaluate Rules| Policies
    
    Gate -->|Allowed| Exec[Execute Tool on Payments DB]
    Exec --> Payments
    Exec -->|Record Execution| Audit
    
    Gate -->|Blocked / Requires 2nd Approver| Suspend[Suspend & Flag Event]
    Suspend -->|Log Reason| Audit
    
    Audit --> ChangeStreams
    ChangeStreams -->|Live Feed| ReviewerUI([Compliance / Approver UI])
    ReviewerUI -->|2nd Approver Sign-off| Gate
```

### MongoDB Collections Design

| Collection | Purpose | Sample Fields |
| :--- | :--- | :--- |
| `identities` | Agents, operators, roles, and active delegation | `id`, `name`, `type` (`agent` \| `human`), `role` (`l1_analyst`, `lead_operator`), `delegated_to`, `active` |
| `policies` | JSON-driven deterministic rules enforced pre-execution | `policy_id`, `action`, `resource`, `conditions` (`amount_max`, `required_approvals`), `effect` (`ALLOW`, `DENY`, `REQUIRE_APPROVAL`) |
| `payments` | Operational payment records and exception states | `payment_id`, `amount`, `currency`, `sender`, `beneficiary`, `status` (`FLAGGED_EXCEPTION`, `HELD`, `RELEASED`), `risk_tier` |
| `audit_events` | Append-only ledger with cryptographic hash chaining | `event_id`, `timestamp`, `trace_id`, `identity_id`, `action`, `tool_name`, `input_args`, `policy_decision`, `reasoning`, `prev_hash`, `hash` |

---

## 3. Key Atlas Features Utilized

1. **Atlas Change Streams:**
   - Powers real-time streaming to the compliance / second-approver interface.
   - Triggers alerts immediately when high-risk policy violations or multi-approver requirements arise.
2. **Schema Validation & Access Controls (RBAC):**
   - Collection-level `$jsonSchema` prevents unauthorized modification or deletion of `audit_events`.
   - The application database user has strictly `insert`-only privileges on `audit_events`.
3. **Cryptographic Hash Chaining (Tamper Evidence):**
   - Each audit document computes `hash = SHA256(prev_hash + timestamp + action + input + decision + output)`.
   - Modifying any historical audit entry breaks the cryptographic chain immediately during audit verification.
4. **Atlas Vector Search (Auditor Querying):**
   - Embeds audit reasoning and exception context.
   - Allows compliance reviewers to query in plain English: *"Show every instance where the agent held a payment exceeding \$20,000 due to velocity flags."*
5. **Atlas Charts / Reviewer Timeline:**
   - Provides visualization for compliance teams to review agent decisions and identify policy bottleneck patterns.

---

## 4. Agent Tools & Pre-Execution Policy Logic

The agent is equipped with standard operational tools, but **cannot invoke them directly without the Atlas policy interceptor**:

```python
# Interceptor Pattern Example
def execute_agent_tool(tool_name: str, args: dict, operator_identity: str):
    # 1. Resolve Identity and Delegated Permissions
    identity = db.identities.find_one({"id": operator_identity})
    
    # 2. Query Policies in Atlas
    policy = evaluate_policy(tool_name, args, identity)
    
    if policy.decision == "DENY":
        log_audit_event(status="BLOCKED", reason=policy.reason)
        return {"error": f"Policy Violation: {policy.reason}"}
        
    if policy.decision == "REQUIRE_APPROVAL":
        log_audit_event(status="AWAITING_APPROVAL", approvers_needed=2)
        return {"status": "HOLD", "message": "Triggered multi-approver requirement."}
        
    # 3. Execute Tool
    result = tools[tool_name](**args)
    
    # 4. Record Hash-Chained Audit Record
    log_audit_event(status="EXECUTED", result=result)
    return result
```

### Tools Defined:
* `get_payment_exception(payment_id)`
* `hold_payment(payment_id, reason)`
* `release_payment(payment_id, destination)`
* `request_supervisor_approval(payment_id, justification)`

---

## 5. Live Demo Flow (5-Minute Script)

1. **Step 1: Task Delegation & Investigation (Allowed)**
   - *Action:* Operator prompts: *"Investigate exception #PAY-10492 and resolve it."*
   - *Behavior:* Agent inspects payment via `get_payment_exception`. Policy checks operator clearance: **ALLOWED**. Audit log records investigation intent.
2. **Step 2: Policy Interception & Hard Block (Pre-Execution Gate)**
   - *Action:* Agent determines payment is valid and attempts `release_payment($75,000)`.
   - *Behavior:* The Atlas Policy Interceptor catches the action. Rule states: *"Releases > \$50,000 require dual-approver sign-off."*
   - *Result:* Action **BLOCKED/HELD**. Atlas stores the reason and pushes a Change Stream event to the dashboard.
3. **Step 3: Human-in-the-Loop Sign-off & Completion**
   - *Action:* Second authorized supervisor reviews the reasoning and signs off via UI.
   - *Behavior:* The agent resumes the workflow, the transaction completes, and both authorizations are permanently logged.
4. **Step 4: Tamper-Evident Audit Verification & Vector Search**
   - *Action:* The auditor view calculates the SHA-256 hash chain of the entire audit trail.
   - *Demo:* A direct database mutation is simulated (e.g., someone attempts to modify the dollar amount in the audit collection). The verification tool flags **"TAMPER DETECTED: Hash mismatch at Block #14"**.
   - *Query:* Auditor asks via Vector Search: *"Find all high-value overrides signed off this morning."*

---

## 6. Implementation Stack & Rules Compliance

### Recommended Tech Stack:
* **Backend:** Python (FastAPI / LangGraph / LangChain tool calling) or Node.js (TypeScript).
* **Database:** MongoDB Atlas (M0/M10 Sandbox cluster with Change Streams, Vector Index, Schema Validation).
* **Frontend:** React + Tailwind or lightweight HTML/SSE (Server-Sent Events) live timeline.

> [!WARNING]
> **Hackathon Rule Warning on Streamlit & Dashboards:**  
> The hackathon guidelines explicitly list **"Streamlit Applications"** and **"Any project where a dashboard is the main feature"** under the **STRICTLY BANNED Anti-Projects**.  
> Ensure your UI is framed strictly as an **Interactive Compliance Reviewer & Approval Terminal**, with the primary focus placed on the **MongoDB Policy Interception Engine & Tool-Calling Agent**.
