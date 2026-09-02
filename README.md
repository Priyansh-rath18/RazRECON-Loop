# 💳 AI Finance Controller

### Evidence-driven reconciliation, investigation, and controlled action — where **AI proposes, and a deterministic policy engine decides.**

> [!IMPORTANT]
> **The AI never has final authority over a financial action.**
>
> Deterministic code establishes facts → AI interprets ambiguous evidence → Policy controls permitted actions → Independent verification checks the outcome.

---

## 🚀 Live Demo

|                   | Link                                                                            |
| ----------------- | ------------------------------------------------------------------------------- |
| 🌐 **Dashboard**  |https://razrecon-loop.streamlit.app/ |
| 📦 **Repository** | `Priyansh-rath18/finance_controller`                                            |

---

# 🎯 The Problem

Payment reconciliation across **orders, payments, refunds, settlements, and bank records** is manual and error-prone.

Finance teams must investigate every mismatch and decide:

* ✅ What is safe to auto-close
* 🔍 What requires human review
* 🚨 What needs escalation
* ⛔ What should **never** be touched

Often, these decisions are made without clear evidence.

Most "AI reconciliation" tools either **automate blindly** or bolt on a chatbot with no real safeguards.

---

# 🧠 The Approach

This project reconciles multi-source payment data **deterministically**, investigates only the exceptions that genuinely require it with an AI agent, and — critically — **never lets that agent have final authority over a financial action.**

A separate **policy engine** gates every decision using:

* AI confidence
* Financial materiality
* Safety rules
* Deterministic constraints

It can therefore:

| Decision           | Meaning                                    |
| ------------------ | ------------------------------------------ |
| 🟢 `AUTO_RESOLVE`  | Safe cases can be automatically resolved   |
| 🟡 `REVIEW`        | Ambiguous cases require lightweight review |
| 🟠 `ESCALATE`      | Cases requiring deeper investigation       |
| 🔴 `REJECT_ACTION` | Unsafe actions are hard-blocked            |

For example, if the AI identifies an over-refund with **95%+ confidence**, the policy engine can still block the action outright.

---

# 🏗️ Architecture

```text
5 SOURCES
Order → Payment → Refund → Settlement → Bank
                    ↓
        ┌─────────────────────────┐
        │ DETERMINISTIC           │
        │ RECONCILIATION           │
        └─────────────────────────┘
                    ↓
          Level 1: Exact Match
             Raw UTR + Amount
                    ↓
       Level 2: Constrained Match
     Normalized UTR + Tolerance
             + Date Window
                    ↓
       Level 3: Extended Identifier
             Normalization
                    ↓
       Duplicate Detection
                    +
       Lifecycle Validation
       Expected vs. Actual Net
                    ↓
            EXCEPTION QUEUE
                    ↓
        ┌─────────────────────────┐
        │ AI INVESTIGATION        │
        │ Gemini                   │
        └─────────────────────────┘
                    ↓
        ┌─────────────────────────┐
        │ Two Architectures       │
        │                         │
        │ • Single-shot           │
        │ • Tool-calling          │
        │                         │
        │ 7 real investigation    │
        │ tools                   │
        └─────────────────────────┘
                    ↓
          PRIORITY SCORING
                    ↓
     ┌─────────────────────────────┐
     │ 6 EXPLAINABLE SIGNALS       │
     │                             │
     │ • Financial exposure       │
     │ • Root-cause risk          │
     │ • Confidence gap           │
     │ • Cash impact              │
     │ • Recurrence               │
     │ • Settlement age           │
     └─────────────────────────────┘
                    ↓
          ┌───────────────────┐
          │ POLICY ENGINE     │
          │ DETERMINISTIC     │
          └───────────────────┘
                    ↓
       ┌────────┬────────┬──────────┬────────────────┐
       │ AUTO   │ REVIEW │ ESCALATE │ REJECT_ACTION │
       │RESOLVE │        │          │               │
       └────────┴────────┴──────────┴────────────────┘
                    ↓
         CONTROLLED EXECUTION
                    ↓
       INDEPENDENT VERIFICATION
                    ↓
      Confidence-based recovery
               routing
                    ↓
              AUDIT TRAIL
                    ↓
          CASH POSITION IMPACT
```

### 🔐 Core Principle

> **Deterministic code establishes facts.**
>
> **The AI interprets ambiguous evidence.**
>
> **Policy controls what actions are permitted.**
>
> **Independent verification checks whether the outcome actually held.**

---

# ✨ What Makes This Different?

## 1️⃣ AI Never Has Final Authority

Every proposed action passes through a **deterministic policy gate**.

A real case in this dataset demonstrates the safety mechanism:

> The agent found an **over-refund at 95%+ confidence** — the policy engine blocked the action outright, regardless of confidence.

---

## 2️⃣ 🔄 Closed-Loop, Confidence-Calibrated Recovery

After any auto-resolved action, an **independent verification pass** re-checks it.

If verification disagrees, the system doesn't blindly escalate.

Instead, it routes based on **why the original decision failed**:

```text
Verification disagrees
        │
        ├── High-confidence miss
        │          ↓
        │       REVIEW
        │
        └── Low-confidence miss
                   ↓
               ESCALATE
```

No financial record is ever modified during recovery.

Only the **case's queue assignment** changes.

---

## 3️⃣ 🔎 Cross-Case Pattern Detection

Individual exceptions are checked for **materially significant clustering**.

Patterns consider:

* Same root cause
* Tight settlement window
* Meaningful combined exposure

This surfaces **systemic issues** instead of treating every case as independent noise.

---

## 4️⃣ 🎯 Resolution Optimizer

This is not just a queue.

Given limited review capacity, the system ranks cases by:

> **Cash-risk-reduction-per-case**

Compliance-critical cases — **policy violations** — are always prioritized regardless of amount.

---

## 5️⃣ 💬 Grounded Natural-Language Q&A

Ask a question about any case in plain English.

Answers are retrieved from the **real audit trail** and synthesized only from that data.

The system does **not** re-investigate the case from scratch.

---

## 6️⃣ 📏 Everything Is Measured

Match rate, precision, recall, and false-resolution rate all come from a **held-out Stage 3 evaluation harness** against seeded ground truth.

These are **not estimates**.

---

# 📊 Evaluation — Stage 3, Held-Out

| Metric                   |      Value |
| ------------------------ | ---------: |
| 🎯 Match rate            |  **96.5%** |
| 🔎 Exception precision   | **100.0%** |
| 📌 Exception recall      |  **90.3%** |
| ⚠️ False-resolution rate |   **9.7%** |
| 📦 Records evaluated     |    **200** |

### What These Metrics Mean

**Match rate** measures how many of the 200 synthetic payment lifecycles were correctly reconciled by the deterministic layer alone.

**False-resolution rate** is the safety-critical number: the rate at which the deterministic layer incorrectly marked something clean when it should have been flagged.

Every one of these cases is individually explainable.

The two categories responsible are:

* `REFUND_TIMING_CONFLICT` — requires temporal reasoning outside deterministic scope by design
* Compound cases with **two co-occurring benign-looking signals**

---

# 🖥️ Dashboard

The dashboard contains **four tabs**, each answering a different question.

### 📊 Executive Overview

* Headline metrics
* System reliability
* Cash forecast
* Cross-case pattern detection
* Resolution optimizer

### 🔍 Exception Operations

* Sortable exception queue
* Settlement Q&A
* Full **9-step Case Journey** per case
* Live **What-If policy simulator**

### 🤖 Agent Control Center

* Real captured tool-calling investigation traces
* **"AI Proposes → Policy Decides"** visual
* `REJECT_ACTION` safety spotlight

### 🔄 System Reliability

* Closed-loop verification & recovery
* Confidence-calibrated re-routing

---

# 🛠️ Tech Stack

| Layer                  | Technology                       |
| ---------------------- | -------------------------------- |
| 🐍 Data & Pipeline     | Python, Pandas                   |
| 🧠 LLM                 | Gemini (`gemini-3.1-flash-lite`) |
| 🔌 LLM SDK             | `google-genai`                   |
| 🤖 Agent Orchestration | LangGraph (single-shot)          |
| 🧰 Tool-Calling Agent  | Native function-calling          |
| 🔧 Investigation Tools | 7 real tools                     |
| 🖥️ Dashboard          | Streamlit                        |
| 📊 Evaluation          | Custom held-out harness          |
| 🎯 Ground Truth        | Seeded synthetic ground truth    |

---

# ⚡ Running Locally

## 1. Clone the Repository

```bash
git clone https://github.com/Priyansh-rath18/finance_controller.git
cd finance_controller
```

## 2. Create & Activate Virtual Environment

```bash
python -m venv venv
venv\Scripts\activate        # Windows
```

## 3. Install Dependencies

```bash
pip install -r requirements.txt
```

## 4. Configure Gemini API Key

Create a `.env` file in the project root:

```env
GEMINI_API_KEY=your_key_here
```

## 5. Run the Dashboard

```bash
streamlit run src/dashboard/app.py
```

---

# 🔁 Regenerating the Pipeline From Scratch

The complete pipeline can optionally be regenerated stage by stage.

### Stage 1 — Synthetic Data + Mutations

```bash
python -m src.generator.generate_data
```

### Stage 2 — Deterministic Reconciliation

```bash
python -m src.matching.match_engine
```

### Stage 3 — Evaluation

```bash
python -m src.eval.evaluate
```

### Stage 4–6 — Agent Investigation + Policy + Audit Trail

```bash
python -m src.agent.audit
```

### Cross-Case Pattern Detection

```bash
python -m src.agent.pattern_detection
```

---

# 📝 Honest Scope Notes

> [!NOTE]
> This project intentionally documents where the system's capabilities end instead of presenting unsupported claims.

### 🧪 Evaluation Environment

200 synthetic payment lifecycles with controlled, seeded ground-truth mutations across **14 exception types**.

No real merchant data or live financial systems are involved.

### 🟡 REVIEW Is a Genuinely Rare Real Outcome

The agent's confidence calibration tends toward decisive answers:

* High confidence
* Clear escalation

rather than the moderate-confidence middle band.

The `REVIEW` policy path is fully implemented and independently verified via **proof-of-capability scenarios** in the System Reliability tab.

In most pipeline runs it does not fire organically, though it has occurred on real data in at least one run.

### 🔎 Settlement Q&A Retrieval

Settlement Q&A uses **keyword-based retrieval**, not semantic search.

This is a deliberate, cheap, deterministic tradeoff.

It is brittle to unusual phrasing but **cannot hallucinate a case that doesn't exist.**

### 🤖 Tool-Calling Agent

The tool-calling agent architecture is demonstrated on a **curated set of captured, real traces** rather than replayed live.

This keeps the dashboard reliable regardless of API quota during a demo.

---

# 🐛 Real Issues Found & Fixed

This project surfaced and fixed a number of genuine bugs.

### 1. Duplicate Bank Entry

A duplicate bank entry was silently missed because one copy had reformatted identifiers.

Raw-string matching found only one candidate.

**Fix:** Added a normalized-identifier safety check.

---

### 2. Circular Fee/Tax Validation

Fee/tax validation initially compared a settlement record against its own — possibly wrong — fee field.

This was a circular check that could never catch a real error.

**Fix:** Rewritten to validate against the true expected formula.

---

### 3. Flat Amount-Blind Tolerance

Flat tolerance thresholds masked small-transaction errors.

**Fix:** Replaced with proportional tolerance.

---

### 4. Production API Failures

Two real API failures occurred in production:

* Daily quota exhaustion → required a model switch
* Transient `503` outage mid-batch → required retry logic with backoff

---

### 5. Missing Audit Schema Field

A field silently missing from saved audit records caused the What-If Simulator to always assume the wrong original decision.

**Fix:** Schema fix + full pipeline re-run.

---

### 6. Noisy Cross-Case Clustering

An early cross-case clustering attempt produced **18 patterns** that were mostly coincidental overlap.

For example, a randomly-assigned payment gateway was carrying no real signal.

**Fix:** Dropped the noisy rule and replaced it with **materiality-filtered, time-window-based clustering.**

---

### 7. Cash-Forecast Backtest

A cash-forecast backtest attempt did not hold up methodologically after two fix attempts.

**Decision:** Deliberately shelved rather than shipped with an unreliable number.

> **The system treats methodological failure as a result worth documenting — not something to hide.**

---

# 🔐 Design Philosophy

```text
                 ┌─────────────────────┐
                 │     RAW SOURCES     │
                 └──────────┬──────────┘
                            ↓
                 ┌─────────────────────┐
                 │ DETERMINISTIC FACTS │
                 └──────────┬──────────┘
                            ↓
                 ┌─────────────────────┐
                 │    AI INVESTIGATES  │
                 │     & PROPOSES      │
                 └──────────┬──────────┘
                            ↓
                 ┌─────────────────────┐
                 │   POLICY ENGINE     │
                 │   DECIDES / BLOCKS  │
                 └──────────┬──────────┘
                            ↓
                 ┌─────────────────────┐
                 │ CONTROLLED ACTION   │
                 └──────────┬──────────┘
                            ↓
                 ┌─────────────────────┐
                 │     VERIFY          │
                 └──────────┬──────────┘
                            ↓
                 ┌─────────────────────┐
                 │    AUDIT TRAIL      │
                 └─────────────────────┘
```

### The fundamental separation:

| Responsibility            | System                           |
| ------------------------- | -------------------------------- |
| Establish financial facts | **Deterministic reconciliation** |
| Investigate ambiguity     | **AI agent**                     |
| Decide what is permitted  | **Deterministic policy engine**  |
| Execute permitted action  | **Controlled execution**         |
| Check outcome             | **Independent verification**     |
| Preserve accountability   | **Audit trail**                  |

---

# 💰 End-to-End Flow

```text
Payment
   ↓
Refund
   ↓
Settlement
   ↓
Bank
   ↓
Deterministic Reconciliation
   ↓
Exception Detection
   ↓
AI Investigation
   ↓
Priority Scoring
   ↓
Policy Decision
   ↓
Controlled Execution
   ↓
Independent Verification
   ↓
Recovery Routing
   ↓
Audit Trail
   ↓
Cash Position Impact
```

---

# 🏆 Track 04 — AI Finance Controller

**Payment → Refund → Settlement → Bank**

### Deterministic Reconciliation

### +

### Agentic Investigation

### +

### Policy-Gated Action

### +

### Independent Verification

---

> **AI proposes. Deterministic policy decides. Independent verification checks.**
>
> Built for **Track 04 — AI Finance Controller**.
