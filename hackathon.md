# Agents in Context Toronto: A MongoDB Hackathon
**Participant Guide & Event Reference**

---

## 📌 Executive Summary & Key Links
* **Host:** [MongoDB](https://cerebralvalley.ai/u/mongodb) & [Cerebral Valley](https://cerebralvalley.ai/e/mongodb-toronto-hackathon)
* **Date:** Saturday, November 14 (9:00 AM – 9:00 PM EST)
* **Submissions Due:** **5:00 PM EST**
* **Project Submission URL:** [Submit Project](https://cerebralvalley.ai/events/~/e/mongodb-toronto-hackathon/hackathon/submit)
* **Discord Community:** [Join Hackathon Discord](https://discord.com/invite/p8N8hApmJ)
* **External Resource Guide:** [MongoDB & Partner Resources Doc](https://docs.google.com/document/d/1rrsNKU3guyvExg_oBPpfOrZF9Ypr5xPLFQ9yYJ2C60o/edit?usp=sharing)
* **Support Email:** `blerta@cerebralvalley.ai` (or ping `@CV` on Discord)

---

## 🎯 Required Problem Statements
Every project **must be built under one of the three problem statements**:

### 1. Agents You Can Audit
> *An agent that can't explain what it did, and who allowed it, never leaves the sandbox.*
* **Objective:** Build an agent using MongoDB Atlas as the identity, policy, and audit layer (collections, schema validation, change streams) that takes real actions across systems. Every action must be tied to an identity, validated against policy before running, and recorded so a reviewer can reconstruct it afterward.
* **Key Questions:**
  * How do you decide what an agent may do and enforce it *before* the action, not after?
  * How do you record what the agent did, why, and under whose authority?
  * How do you stop or roll back an agent mid-run?
* **Examples:**
  * Claims-handling agent with per-step policy gates and a queryable audit ledger.
  * KYC-refresh agent strictly blocked from touching accounts outside its designated scope.

### 2. Memory You Can Govern
> *What an agent remembers is data someone has to answer for.*
* **Objective:** Build an agent using MongoDB Atlas and Vector Search to persist and retrieve memory such that memory alters subsequent runs—with strict rules for access control, expiration, and correction.
* **Key Questions:**
  * How do you prevent one client’s or team’s memory from leaking into another’s?
  * How does the agent fix or drop inaccurate or expired memory?
  * How do you prove that memory changed agent behavior rather than just inflating prompt tokens?
* **Examples:**
  * Advisor-prep agent with memory strictly scoped per client and per advisor.
  * Incident-triage agent that recalls historical fixes and enforces TTL/expiration.

### 3. Finish the Job
> *Real work spans many systems and takes hours, and the systems won't hold still.*
* **Objective:** Build an agent that completes long multi-step workflows across systems, using MongoDB Atlas to persist verified task state and Vector Search to retrieve past experience, making it resilient to crashes and schema/UI drift.
* **Key Questions:**
  * How does it distinguish an action that took effect from one that was only transmitted?
  * How does it resume cleanly after a crash without replaying the entire history?
  * How does it adapt when layouts, fields, or workflows mutate underneath it?
* **Examples:**
  * Address-change agent updating multiple systems that recovers and retries only failed steps when a system refreshes mid-run.
  * Month-end financial reconciliation agent resuming seamlessly from checkpointed, verified state.

---

## 🚫 Strictly Banned Projects ("Anti-Projects")
Projects will face **immediate disqualification** if they fall into any of the following categories:
- ❌ Basic RAG Applications
- ❌ Streamlit Applications
- ❌ AI Mental Health Advisor
- ❌ AI for Education Chatbot
- ❌ AI Job Application Screener
- ❌ AI Nutrition Coach
- ❌ Personality Analyzers
- ❌ Image Analyzers
- ❌ Sports Analyzers or Coaches
- ❌ Any project using AI to give medical advice
- ❌ Any project where a dashboard is the primary feature

---

## 📜 Key Hackathon Rules
1. **Mandatory MongoDB Atlas Sandbox:** Finalists **must** build their project using the hackathon-provided MongoDB Atlas Sandbox. Projects outside the sandbox will not be eligible for final judging or prizes.
2. **Open Source & Public Repos:** All code repositories must be public.
3. **Team Size:** Up to 4 members per team (Solo hackers allowed).
4. **New Work Only:** Projects must be built during the event. Existing codebases or unoriginal work will result in immediate disqualification.
5. **Submission Video Requirement:** Teams must provide a **1-minute demo video** showcasing only functionality and code built during the hackathon.

---

## ⏰ Detailed Schedule
| Time | Milestone / Activity |
| :--- | :--- |
| **9:00 AM** | Doors Open, Breakfast Served, Team Formation |
| **10:00 AM** | Welcome & Kick-Off Presentations |
| **10:45 AM** | 🚀 **Hacking Officially Begins** |
| **11:00 AM** | Deadline to check in for ElevenLabs Creator tier perks |
| **1:00 PM** | 🥪 Lunch Served |
| **5:00 PM** | 🏁 **Submissions Due** (Form closes) |
| **5:15 PM – 6:45 PM** | **Round 1 Judging** (Breakout rooms) |
| **6:00 PM** | 🍕 Dinner Served |
| **7:00 PM – 8:00 PM** | **Round 2 Final Judging** (Top 6 teams on main stage) |
| **8:15 PM** | 🏆 **Winners Announced** |
| **9:00 PM** | Doors Close |

---

## ⚖️ Judging Criteria & Process

### Round 1: Room Breakouts
* **Format:** ~3-minute live demo + 1–2 minutes Q&A.
* **Scoring Breakdown:**
  * **Technical Demo (35%):** Is it well-engineered, operational, and impressive live?
  * **Implementation Difficulty (30%):** Does it exhibit true technical depth beyond simple prompt engineering?
  * **Impact Potential (20%):** Does it address a significant real-world operational problem?
  * **Creativity (15%):** Originality and unique approach.

### Round 2: Main Stage Finals
* **Format:** Top 6 teams demo live on stage (3-minute demo + 2 minutes Q&A) before the entire audience and judge panel.
* **Scoring:** The same 4 criteria weighted equally (25% each).

---

## 🏆 Prizes
* **🥇 1st Place:** \$7,000 USD (MongoDB) + \$3,000 LangSmith Credits + 3 Months ElevenLabs Pro Tier
* **🥈 2nd Place:** \$5,000 USD (MongoDB) + \$2,000 LangSmith Credits + 3 Months ElevenLabs Pro Tier
* **🥉 3rd Place:** \$3,000 USD (MongoDB) + \$1,000 LangSmith Credits + 3 Months ElevenLabs Pro Tier
* **🎙️ Best Project Built with ElevenLabs:** 3 Months ElevenLabs Scale Tier
* **🎁 Participant Perk:** 1 Free Month of ElevenLabs Creator Tier (Check in before 11:00 AM)

---

## 📍 Logistics & Venue
* **Location:** The Quay, 3rd Floor, 100 Queens Quay E, Toronto, ON M5E 1V3
* **Directions:** ~15-minute walk from Union Station. Lobby entrance is off Queens Quay East, right of the LCBO doors.
* **Wi-Fi Network:** `TRBOT-Guest`
* **Parking:** Impark Lot #526 (Entry via Cooper St. or John M. Tinsley St.). Rates: \$10/hr, \$25 day max (6 AM–6 PM), \$15 evening flat rate (6 PM–6 AM).
* **ID:** Government-issued photo ID required.

---

## 👥 Judges & Mentors
* **Robert Maissan** – Senior Lead, Engineering @ MongoDB
* **Raschid Jimenez** – Senior Product Manager @ MongoDB
* **Tapan Shah** – Staff Engineer @ MongoDB
* **Leo Gomes** – Full Stack Software Developer @ Pelmorex
* **Aasawari Sahasrabuddhe** – Senior Builder Advocate @ Okta
* **Sergey Strelnikov** – VP of Engineering @ Acerta
* **Anamika Ahmed** – Senior Software Engineer @ Microsoft
* **Pablo Vallejo** – Engineering Manager @ Wealthsimple
* **Amrit Krishnan** – Technical Lead @ Vector Institute
* **Vatsal Shah** – Co-Founder & CTO @ Speak AI
* **Parth Patel** – Forward Deployed Engineer @ Cohere
* **Ahmed Radwan** – Applied ML @ Vector Institute
* **Pahul Hallan** – Senior Machine Learning Engineer @ Zafin
* **Noel Kirthiraj** – Founder & Principal @ Omni
* **Rudraksh Monga** – Senior Software Engineer @ Stan
* **Aasheesh Singh** – Senior Research Engineer @ Quantiphi
*(And additional mentors on-site)*
