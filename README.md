# Transactions Monitor: Auditable Payment Exception Resolution Agent

> Built for **Agents in Context Toronto: A MongoDB Hackathon**  
> Problem Statement: **Problem 1 – Agents You Can Audit**

---

## 📌 Overview

Financial operations teams handle high volumes of payment exceptions (e.g., sanctioned accounts, mismatched routing numbers, suspicious velocity, or over-limit transfers). 

**Transactions Monitor** is an autonomous AI operations agent that investigates and resolves payment exceptions. Rather than granting unconstrained execution permissions, **every single tool call is intercepted by a MongoDB Atlas governance layer** that enforces:

1. **Identity & Delegation:** The agent acts explicitly on behalf of an authenticated human operator with defined roles and delegations (`Agent X` acts for `User Y`).
2. **Pre-Execution Policy Gates:** Deterministic policies evaluated *before* execution (e.g., holds under \$10K permitted, releases over \$50K require secondary human approvers, no access to VIP PII).
3. **Immutable, Tamper-Evident Audit:** An append-only ledger in MongoDB Atlas capturing intent, policy decisions, tool inputs/outputs, reasoning, and cryptographic hash chains.
4. **Real-time Change Streams:** Real-time visibility into agent actions, flags, and approvals via MongoDB Atlas Change Streams.

---

## 🏗️ Architecture

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
    
    Gate -->|Blocked / Requires Approver| Suspend[Suspend & Flag Event]
    Suspend -->|Log Reason| Audit
    
    Audit --> ChangeStreams
    ChangeStreams -->|Live Feed| ReviewerUI([Compliance / Approver UI])
    ReviewerUI -->|Sign-off| Gate
```

---

## 🚀 Getting Started

### 1. Prerequisites
- Python 3.10+ or Node.js (depending on service stack)
- MongoDB Atlas cluster (M0 or higher) with Change Streams enabled

### 2. Environment Setup
Copy the example environment configuration:
```bash
cp .env.example .env
```
Fill in your `MONGODB_URI` and LLM API keys in `.env`.

---

## 📁 Repository Structure
```
.
├── .env.example                     # Environment variables template
├── .gitignore                       # Git ignore rules for secrets and build artifacts
├── README.md                        # Project documentation
├── hackathon.md                     # Hackathon rules & reference guide
└── payment_exception_audit_agent.md # Detailed system spec & Atlas schema design
```
