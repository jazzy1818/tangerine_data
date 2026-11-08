# 🍊 Tangerine Mission Control: Master Implementation Guide & Team Execution Roadmap
**Sheridan Datathon 2026 — Track: Tangerine ("Resilience Rewired")**
*Comprehensive Technical Documentation, Unified Architectural Blueprint, and 3-Person Team Division Plan*

---

## Executive Summary

This document serves as the master blueprint for your team at the Sheridan Datathon 2026. It accomplishes three critical objectives:
1. **Documents Everything Built from Scratch:** A complete technical, mathematical, and architectural breakdown of the working prototype currently running in your repository.
2. **Bridges Current Code with the Team's Plan:** A unified roadmap harmonizing our working engine with the team's **NASA Mission Control / Safe Mode** conceptual brief and the **8-Module Taxonomy (`M1`–`M8`)**.
3. **Divides Work Across Your 3-Person Team:** A balanced, specialized task matrix tailored specifically for **2 Computer Science / Coding specialists** and **1 Finance / Business specialist**.

---

# Part I: What Has Been Built (From Scratch)

### 1. The Challenge & Judging Rubric
The **Tangerine Track ("Resilience Rewired")** evaluates solutions on four distinct pillars:
- **Discovery (35%):** Finding non-obvious, actionable behavioral patterns in the historical data.
- **Data Use (25%):** Strict adherence to the organizer's mathematical baseline formulas across 4,500 bank accounts.
- **Communication (25%):** Clarity of the pitch, defensibility of assumptions, and user-centric explanation.
- **Impact (15%):** Practical feasibility (no fake income, unverified debt approvals, or fabricated insurance benefits).

The judging format is a strict **5-minute evaluation**:
- **Minute 1:** High-impact pitch introducing the core discovery.
- **Minutes 2–4:** Live demonstration on a random judge-selected customer and shock.
- **Minute 5:** Technical & financial Q&A.

---

### 2. The Raw Dataset Architecture
Located in [`Tangerine/data/`](file:///Users/jaskarannarula/Downloads/Datasets/Tangerine/data), the dataset contains multi-table records from **January 2020 through December 31, 2025**:

```
                       DATA RELATIONSHIPS
                       
    [clients.csv] ──(client_id)──┐
                                 ▼
                          [dispositions.csv]
                                 ▲
    [accounts.csv] ──(account_id)┴──────────┬──────────────┐
           │                                │              │
           ▼                                ▼              ▼
 [monthly_summary.csv]             [loans.csv]   [standing_orders.csv]
           │                                               │
           ▼                                               ▼
  [transactions.csv] ◄─────────────────────────────────────┘
  (1,056,320 rows)
```

- **`accounts.csv` (4,500 rows):** Account IDs, creation dates, statement frequency, district links.
- **`clients.csv` (5,369 rows):** Client demographics (birth date, gender, district).
- **`dispositions.csv` (5,369 rows):** Relational links mapping clients to accounts as `OWNER` or `DISPONENT` (caretaker).
- **`loans.csv` (682 rows):** Contractual debt records: amount, start date, duration, monthly payment $P$, and status (`A` repaid, `B` in default, `C` running OK, `D` running in debt).
- **`standing_orders.csv` (6,471 rows):** Automated monthly debits for household bills, leasing, and loan payments.
- **`monthly_summary.csv` (26,846 rows):** Aggregated monthly financial data: `money_in`, `money_out`, `household_bills`, `loan_payments`, `avg_daily_balance`, `min_balance`, `days_below_zero`.
- **`transactions.csv` (1,056,320 rows):** Full dated transaction ledger: cash deposits, withdrawals, credit/debit card purchases, fees, and interest payments.

---

### 3. The Mathematical Baseline Engine (Pillars 1 & 2)
The organizer README defines strict formulas that must be calculated with unrounded mathematical precision. Implemented in [`engine.py`](file:///Users/jaskarannarula/Downloads/Datasets/Tangerine/engine.py):

#### A. Know the Customer (Baseline Numbers)
For any `account_id`:
1. **$I$ (Typical Monthly Income):** $\text{Median}(\text{money\_in})$
2. **$S$ (Typical Monthly Spending):** $\text{Median}(\text{money\_out})$
3. **$F$ (Fixed Costs):** $\text{Median}(\text{household\_bills} + \text{insurance} + \text{loan\_payments})$
4. **$B$ (Savings Buffer):** $\text{Mean}(\text{avg\_daily\_balance})$ across the **last 6 months** (July–Dec 2025).
5. **$H$ (Household Bills):** $\text{Median}(\text{household\_bills})$
6. **$P$ (Active Loan Monthly Payment):** Active loan monthly payment if status is running (`C` or `D`); otherwise $0.00$.

#### B. The Official Runway Formula
$$\text{buffer\_left} = B - \text{one\_off\_costs}$$
$$\text{gap} = S_{shock} - I_{shock}$$
$$\text{Runway} = \begin{cases} 
0.0 & \text{if } \text{buffer\_left} \le 0 \\
\text{"no shortfall (120+)"} & \text{if } \text{gap} \le 0 \\
\min\left(\frac{\text{buffer\_left}}{\text{gap}}, 120.0\right) & \text{otherwise (rounded to 1 decimal for display)}
\end{cases}$$

#### C. Verification & Auditing
- **Float Precision Fix:** We resolved earlier 0.1-month rounding drift by preserving raw unrounded floats (`raw_I, raw_S, raw_B, raw_F, raw_H, raw_P`) throughout intermediate calculations.
- **Verification Result:** Ran **22,500 automated scenario comparisons across all 4,500 accounts** against the README rules: **0 mismatches (100% agreement)**.

---

### 4. The Two Required Plans (Pillar 3)
Built in `engine.make_plan()`:

#### Plan 1: The Goal Plan (Normal Times)
- **Target Emergency Fund:** Sized to 3 months ($3 \times S$) and 6 months ($6 \times S$) of typical spending.
- **Monthly Surplus:** Calculated as $I - S$.
- **Funding Status & Horizon:** Progress bar measuring current buffer $B$ against targets; calculates months to fully fund at a realistic 70% surplus contribution rate.

#### Plan 2: The Backup Plan (Active Shock Response)
- **Customer-Confirmed Discretionary Cut:** Slices trimmable variable spending ($S - F$) while keeping shelter, utilities, and debt payments intact.
- **Month 0 Immediate Overdraft Detection:** Fixed a critical bug where accounts with large surprise repairs (e.g. Account `26967` with a $\$11,531$ furnace repair) overdraw immediately on Day 0. The plan explicitly flags Month 0 failure rather than masking it with Month 1 surplus.
- **6-Month Schedule Table:** Generates a month-by-month trajectory tracking opening balance, money in, money out, net deficit, and closing balance.
- **Statutory 6-Month Benefit Limits:** Models Canadian Employment Insurance (EI 55%) as expiring after 6 months to avoid inflated 120-month rescue claims.

---

### 5. The Breakthrough Pitch Discovery: The 131-Account Liquidity Trap
This is your team's primary **Discovery (35% score)** weapon:

#### The Problem With Standard Banking
Every existing banking tool looks at monthly aggregates ($I - S$). If an account nets positive at the end of the month, the bank reports zero risk.

#### The Reality: Timing Mismatches
We simulated day-by-day cash flows across all **4,500 accounts** through the 180-day shock replay (July 1 to December 31, 2025):
- **131 accounts went negative between month-ends**, despite closing every monthly cycle with a positive balance.
- Why? **Their fixed household bills debited days before their paychecks arrived.**
- **103 accounts** had recognizable recurring household bills.
- **43 of those 103 (41.7%) were completely saved from overdraft** purely by shifting their household bill by **7 days** to fall after their paycheck.
- **Net Cost to Customer:** **$\$0.00$**. Zero extra income required, zero lifestyle sacrifice, and zero change to month-end balances.
- **The Catch:** Date changes require **biller/landlord approval**.

---

### 6. The "Survive a NO" Interactive Engine
Implemented in [`daily_simulation.py`](file:///Users/jaskarannarula/Downloads/Datasets/Tangerine/daily_simulation.py), [`gemini_advisor.py`](file:///Users/jaskarannarula/Downloads/Datasets/Tangerine/gemini_advisor.py), and Tab 4 of [`app.py`](file:///Users/jaskarannarula/Downloads/Datasets/Tangerine/app.py):

#### The Live Demo Anchor: Account `22812`
- **Inflow:** Salary deposit hits on the **12th** of each month ($\sim$\$14,271).
- **Outflow:** Household bill debits on the **7th** (\$2,350.32) — **5 days before paycheck arrival**.
- **Under Layoff (55% EI) + 15% Bills:**
  - **Unprotected Baseline:** First overdraft occurs on **Nov 07, 2025**, with a peak deficit of **$\$8,401.28$**.
  - **Judge Clicks [✅ YES — Biller Approved]:**
    - Household bill shifts to Nov 14 (after deposit).
    - First shortfall is delayed by **27 days** (to **Dec 04, 2025**).
    - Peak cash deficit drops to **$\$5,698.41$**.
    - **Honesty:** The engine visibly displays that $\$5,698.41$ in starting cash or budget trimming is still required over 6 months.
  - **Judge Clicks [❌ NO — Biller Denied]:**
    - The engine immediately strikes `move_recurring_bill` from viable actions.
    - Recalculates cash flows in real time and automatically pivots to **Discretionary Spending Cuts** or **Repair Installment Splitting**.
  - **Combined Resilience:** Shifting the bill 7 days + confirming a modest 15% discretionary cut keeps Account 22812 **100% solvent through all 6 months with $\$14,372.20$ remaining**.

---

### 7. Gemini 2.5 Flash SDK Integration & Zero-PII Boundary
Built in [`gemini_advisor.py`](file:///Users/jaskarannarula/Downloads/Datasets/Tangerine/gemini_advisor.py):
- **Structured Pydantic Output (`AdvisorPlan`):** Forces the model to return typed JSON (`primary_action_id`, `confirmation_question`, `requires_third_party_approval`, `approval_entity`, `rationale`, `fallback_action_id`).
- **Strict Privacy Isolation:**
  - **NEVER SENT:** Client IDs, account IDs, names, birth dates, raw transactions, or exact balances.
  - **COARSE TOKENS ONLY:** Shock type, allowed action IDs, days to shortfall, and coarse deficit tiers.
- **Zero-Fail Deterministic Fallback:** If `GEMINI_API_KEY` is not provided or network times out, the local rule engine provides seamless operation.

---

### 8. Phase P5 Enhancements Already Completed
- **Live ETF & Market Intelligence ([`etf_service.py`](file:///Users/jaskarannarula/Downloads/Datasets/Tangerine/etf_service.py) & Tab 5):** Real-time Yahoo Finance API queries for Canadian and global index ETFs (`VFV.TO`, `XEQT.TO`, `CASH.TO`), any-ticker search, and honest `N/A (Feed Offline)` handling.
- **Wealth Waterfall & Down Payment Milestone (Tab 3):** Routes surplus into emergency buffers, TSX index funds, and homeownership down payments ($CAD \$25k–\$250k).
- **Underwritten Protection Shields (Tab 3):** Simulates Job Loss, Critical Illness, and Mortgage Defense policies with capped 6-month payouts and premium deductions.

---

# Part II: The Unified Plan (What to Do from Now)

To merge your existing prototype with your team’s **NASA Mission Control** brief, execute these five structured phases:

```
┌────────────────────────────────────────────────────────────────────────────┐
│                       UNIFIED 5-PHASE ROADMAP                              │
├───────────────────┬───────────────────┬────────────────────────────────────┤
│ Phase 1: Branding │ Phase 2: Taxonomy │ Phase 3: Head-to-Head Arena        │
│ NASA Safe Mode    │ Standardize on    │ Add Selector Toggle:               │
│ Status Indicator  │ M1 to M8 Action   │ JEFF Rules vs Gemini 2.5 Flash     │
│ (Normal/Prot/Emg) │ Framework IDs     │ on identical input vectors         │
├───────────────────┴───────────────────┴────────────────────────────────────┤
│ Phase 4: Free-Text Shock Translator (NLP to Typed Financial Effects)       │
├────────────────────────────────────────────────────────────────────────────┤
│ Phase 5: 5-Minute Pitch Deck & Live Demonstration Rehearsal                │
└────────────────────────────────────────────────────────────────────────────┘
```

### Phase 1: Adopt the NASA Mission Control & Safe Mode Theme
Add an automated **Financial Safe Mode** indicator to the top of the interface:
- **`NORMAL` (Green):** Baseline runway $\ge 6$ months, 3-month emergency buffer fully funded, positive cash surplus.
- **`PROTECTION` (Amber):** Active shock, runway between 3 and 6 months, or discretionary cuts actively buffering fixed costs.
- **`EMERGENCY` (Red):** Runway $< 3$ months, immediate Month 0 deficit, or essential debt obligations threatened.

### Phase 2: Formalize the 8-Module Response Taxonomy (`M1`–`M8`)
Tag all existing actions and recommendations with the team's official taxonomy:
- `M1: Income Continuity` (Layoffs, EI benefits, severance).
- `M2: Cost Rebalancing` (Discretionary cuts, inflation mitigation).
- `M3: Emergency Liquidity` (One-off expense handling, repair installment splits).
- `M4: Debt & Obligation Defense` (Loan payment deferral, hardship relief).
- `M5: Multi-Shock Stabilization` (Coordinated multi-crisis defense).
- `M6: Reserve Restoration` (Systematic rebuilding of emergency fund).
- `M7: Cash-Flow Timing & Access` (7-day bill shifting, paycheck alignment).
- `M8: Surplus & Windfall Allocation` (Wealth Waterfall, down payment, index ETFs).

### Phase 3: The JEFF vs. Gemini Head-to-Head Selector Arena
Surface a clean toggle in Tab 4:
- **Selector Toggle:** `[⚡ JEFF Deterministic Engine] vs [🤖 Gemini 2.5 Flash]`
- Both receive the **exact same canonical inputs**: `CustomerFeatures + ShockEffects + FinancialConstraints`.
- Both return the **exact same JSON schema**: `lead_module`, `support_modules`, `rationale`.
- The shared **Deterministic Finance Engine** acts as referee, sizing the dollar amounts and simulating cash flow.
- Highlights: **JEFF** offers 0ms local execution; **Gemini** provides natural-language contextual rationale.

### Phase 4: Universal Free-Text Shock Translator
Add an optional natural-language input field where a judge can type:
> *"I lost my job, bills went up 15%, and my transmission blew costing $1,500."*
- Gemini extracts structured JSON:
  `{"income_multiplier": 0.55, "bills_increase_pct": 0.15, "one_off_costs": 1500}`
- Operator can review/edit the numbers live before running the simulation.

### Phase 5: Pitch Deck & Live Rehearsal
Prepare a crisp 5-slide deck and run timed dry runs of the 5-minute presentation.

---

# Part III: Team Work Division & Responsibility Matrix

Based on your team structure (**2 Computer Science / Coding specialists + 1 Finance specialist**), here is the balanced workload distribution:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          3-PERSON TEAM ALLOCATION                           │
├───────────────────────┬───────────────────────┬─────────────────────────────┤
│ PERSON 1 (CS Lead)    │ PERSON 2 (Full-Stack) │ PERSON 3 (Finance Lead)     │
│ Backend / AI / Solvers│ Frontend / UI / Demo  │ Analysis / Pitch / Defense  │
├───────────────────────┼───────────────────────┼─────────────────────────────┤
│ • Shock NLP Translator│ • NASA Safe Mode UI   │ • Empirical Discovery Lead  │
│ • JEFF vs Gemini Eval │ • M1–M8 Badge Styling │ • Macro Chart & Denominators│
│ • Module Crosswalk    │ • Biller YES/NO UI    │ • Pitch Deck & Script       │
│ • Zero-PII Validation │ • Plotly Enhancements │ • Live Judge Q&A Defense    │
└───────────────────────┴───────────────────────┴─────────────────────────────┘
```

---

### Person 1: CS Specialist A (Backend, AI & Financial Solver Lead)
**Core Mission:** Model logic, structured schemas, AI reasoning, and evaluation suite.

#### Specific Responsibilities & Deliverables:
1. **Free-Text Shock NLP Parser (`shock_parser.py`):**
   - Create a module using Gemini 2.5 Flash to take natural-language judge text and convert it into structured JSON matching `take_shock()` arguments.
   - Include manual overrides so any value can be hand-tuned if needed.
2. **JEFF vs. Gemini Selector Adapter (`selectors.py`):**
   - Formalize the selector interface: `select_plan(features, shock, backend="jeff"|"gemini")`.
   - Ensure both output identical Pydantic structures (`lead_module`, `support_modules`, `rationale`).
3. **8-Module Crosswalk Mapping:**
   - Update [`shock_playbook.json`](file:///Users/jaskarannarula/Downloads/Datasets/Tangerine/shock_playbook.json) to explicitly tag all actions with `M1` through `M8`.
4. **Automated Evaluation Suite (`evaluate.py`):**
   - Build a test script running 10 representative shocks through both JEFF and Gemini.
   - Log latency, schema validity, and financial safety violations (must be 0%).

---

### Person 2: CS Specialist B (Full-Stack, UI/UX & Live Demo Lead)
**Core Mission:** Streamlit presentation, visual safe modes, interactive controls, and rock-solid demo flow.

#### Specific Responsibilities & Deliverables:
1. **NASA Mission Control & Safe Mode Header:**
   - Add a high-visibility status pill to the top of `app.py`:
     - 🟢 `SAFE MODE: NORMAL`
     - 🟡 `SAFE MODE: PROTECTION ACTIVE`
     - 🔴 `SAFE MODE: EMERGENCY FAULT`
2. **Selector Toggle in Tab 4:**
   - Add a radio button in Tab 4: `Recommendation Engine: [⚡ JEFF Rules] vs [🤖 Gemini 2.5 Flash]`.
   - Display side-by-side comparison of JEFF vs Gemini module choices and explanations.
3. **M1–M8 Module Badges:**
   - Style the action cards in Tab 3 and Tab 4 with crisp badges (e.g. `[M7: CASH-FLOW TIMING & ACCESS]`, `[M2: COST REBALANCING]`).
4. **Interactive Plotly Chart Polishing:**
   - Enhance the daily balance trajectory chart in Tab 4:
     - Add milestone markers (e.g. "Nov 7: Baseline Shortfall", "Nov 14: Shifted Bill", "Dec 4: Delayed Shortfall").
5. **Fail-Safe Demo Mode:**
   - Ensure all preset buttons and inputs run cleanly offline with zero spinner lag during live judging.

---

### Person 3: Finance & Business Specialist (Financial Validation & Pitch Lead)
**Core Mission:** Financial truth, discovery storytelling, pitch presentation, and judge defense.

#### Specific Responsibilities & Deliverables:
1. **Lead the 1-Minute Pitch & Storyline:**
   - Craft and deliver the opening hook:
     > *"Most banking apps tell you what you spent last month. Tangerine Mission Control asks: What happens when life hits? In space, when an anomaly strikes, Mission Control doesn't guess—it drops into Safe Mode, isolates essentials, and replans around actual fuel. We brought that to personal finance."*
2. **Master the 131-Account Discovery Story (35% Score):**
   - Own the data explanation of the July–December 2025 replay:
     - 131 accounts went negative between month-ends despite clearing monthly close positive.
     - 103 had recognizable monthly household bills.
     - Shifting the bill 7 days saved 43 accounts (41.7%) with $\$0.00$ cost.
   - Explain why monthly averages conceal risk.
3. **Verify All Numbers & Defend Constraints During Q&A:**
   - Ensure no unrealistic claims are made (e.g., defend why Account 22812 still requires $\$5,698$ in buffer after bill shifting).
   - Explain Canadian statutory EI benefits (55% earnings cap for 6 months).
4. **Slide Deck & Competition Submission Artifacts:**
   - Create a clean 5-slide deck matching the 5-minute rubric.
   - Ensure `README.md` and repository links are ready for submission.

---

# Part IV: The 5-Minute Winning Pitch Script

Here is the exact rehearsal script for your live presentation:

### Minute 0:00 – 1:00: The Opening Pitch (Finance Lead)
> *"Judges, financial vulnerability is rarely a total lack of money—it is a failure of timing and resilience. Standard banking apps calculate monthly averages and tell customers they're safe. But life doesn't happen in monthly averages.*
>
> *Our discovery across 4,500 real Tangerine accounts revealed that in a simulated crisis, **131 accounts plunged into overdraft between month-ends**, despite closing every month positive. Why? Their fixed household bills debited 5 days before their paychecks arrived. By shifting their bill date just 7 days, we eliminated overdrafts for **41.7% of them with zero extra dollars required**.*
>
> *Inspired by NASA aerospace fault management, we built **Tangerine Mission Control**. It detects the shock, triggers an appropriate Financial Safe Mode, and replans around the customer's actual resources."*

---

### Minute 1:00 – 2:30: Live Customer Profiling & Shock (CS Lead B at the controls)
> *"Let's test Account 22812—a single-owner account with high cash flow. Tab 1 profiles their baseline: $14.5k monthly income, $14.8k spending, and $51k in buffer.*
>
> *Now let's apply a severe twist: an unexpected layoff cutting income to 55% under statutory EI, plus a 15% utility inflation hike. In Tab 2, their monthly gap widens to $7,180, and their safe mode drops from `NORMAL` to `EMERGENCY`.*
>
> *Tab 3 immediately generates both required plans: Plan 1 builds their normal-times emergency buffer; Plan 2 maps their 6-month shock trajectory with customer-confirmed discretionary cuts."*

---

### Minute 2:30 – 4:00: The "Survive a NO" & JEFF vs Gemini Showdown
> *"Now for the showstopper in Tab 4. We compare our two selectors: the team's JEFF rule classifier and Gemini 2.5 Flash with structured outputs. Both analyze the customer's cash flow and agree on lead module **`M7: Cash-Flow Timing & Access`**.*
>
> *Their household bill debits on the 7th; their paycheck lands on the 12th. The advisor asks: **'Can we move your bill payment 7 days to fall after your deposit?'***
>
> *If the judge clicks **YES**, the engine shifts the payment to the 14th. Watch the daily chart: it delays the first overdraft by **27 days**, cutting the deficit from $8,401 to $5,698. But we don't promise a magical fix—we honestly show the remaining $5,698 gap.*
>
> *Now, what if the landlord or biller says **NO**? Watch: The judge clicks **NO**. The engine immediately strikes `M7`, enters `EMERGENCY` safe mode, and recalculates alternative options—pivoting to **`M2: Cost Rebalancing`** for an immediate 30% discretionary cut, fully restoring solvency!"*

---

### Minute 4:00 – 5:00: The Long-Term Wealth Bridge & Q&A
> *"Once stabilized, Tab 5 connects survival to long-term wealth: our Wealth Waterfall directs post-crisis surplus into liquid TSX index ETFs (`VFV.TO`, `XEQT.TO`, `CASH.TO`) via live market feeds to fund their first home down payment.*
>
> *Tangerine Mission Control gives customers a plan that survives real life. We're ready for your questions."*

---

# Part V: Action Checklist for Today

- [ ] **Person 1 (Backend/AI):**
  - Add `M1`–`M8` module labels to [`shock_playbook.json`](file:///Users/jaskarannarula/Downloads/Datasets/Tangerine/shock_playbook.json).
  - Add free-text NLP shock translator helper to [`gemini_advisor.py`](file:///Users/jaskarannarula/Downloads/Datasets/Tangerine/gemini_advisor.py).
  - Formalize the JEFF vs Gemini selector comparison functions.

- [ ] **Person 2 (Frontend/Demo):**
  - Add the NASA `Financial Safe Mode` badge (`NORMAL` / `PROTECTION` / `EMERGENCY`) to the header in [`app.py`](file:///Users/jaskarannarula/Downloads/Datasets/Tangerine/app.py).
  - Add the `[⚡ JEFF Rules] vs [🤖 Gemini 2.5 Flash]` toggle in Tab 4.
  - Test UI on mobile and desktop viewports.

- [ ] **Person 3 (Finance/Pitch):**
  - Create the 5-slide presentation deck.
  - Memorize the exact numbers: 131 intra-month shortfall accounts, 103 with bills, 43 saved (41.7%), Account 22812 buying 27 days before shortfall.
  - Lead timed rehearsals of the 5-minute presentation.
