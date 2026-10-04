## 1. Header

- Title: Search for past meetings
- Owner: Product Manager
- Status: Draft for Human Gate A, blocked on the plan-level decision (Q-1)
- Version: 0.1
- Run ID: 2026-01-15-contradictory-decisions
- Problem framing: 02-problem.md (primary problem PB-1)

## 2. TL;DR

Users want better ways to find past meetings (P-1), and a large prospect worth $200K annually specifically asked for search (R-1, M-1). The proposed direction is a search feature for past meetings (S-1), but which plan levels get it at launch is an open disagreement that leadership must decide (DIS-1, Q-1). The proposed primary success metric is the share of search users who find the past meeting they were looking for, with no baseline yet.

## 3. Problem statement

Users want better ways to find past meetings (P-1). A large prospect that uses the Standard and Enterprise plans depending on the department specifically asked for search (R-1, U-1). Validation status: VALIDATED on thin evidence in the problem framing (PB-1). The notes give no counts or research beyond the PM's statement and the prospect's request, no step-by-step scenario, and no description of how users find past meetings today. The deal with the prospect is worth $200K annually (M-1).

## 4. Why now and strategic fit

- A deal with a large prospect is pending and is worth $200K annually (R-1, M-1).
- The prospect needs an answer by end of week (M-2).
- The Sales Lead says search on all plan levels was promised to the prospect (R-2).
- The Product Marketing Lead sees search as an Enterprise differentiator that helps the pricing story (R-3). This conflicts with the Sales Lead's view and is not resolved (DIS-1). See Open questions.
- The notes give no wider strategy statement and no roadmap decision. No decisions were made in the meeting.

## 5. Target users and segments

For: users who need to find past meetings (P-1), including the large prospect, which uses the Standard and Enterprise plans depending on the department (U-1).

Not for: not decided. Whether Standard plan users are in or out of v1 depends on the open plan-level decision (Q-1).

## 6. Evidence

### 6a. Data insights

No data provider configured. The only figures in the notes were reported verbally in the meeting. They are not verified by a data provider and have no evidence card.

- The deal with the large prospect is worth $200K annually (M-1). This is the Sales Lead's statement.
- The prospect needs an answer by end of week (M-2).

There is no usage or search data in the notes.

### 6b. Customer anecdotes

No anecdote provider configured. No anecdote records exist for this run.

- A large prospect specifically asked for search (R-1). The Sales Lead says it was promised search on all plan levels (R-2). This is reported second hand and frequency is unknown.
- No counter-anecdote was raised in the notes.

### 6c. Evidence gaps

- No data provider: the deal value (M-1) comes from a verbal report. How to close: the Sales Lead confirms the deal value and what exactly was promised to the prospect (R-2).
- No evidence that users in general want search beyond the PM's statement and one prospect (P-1, R-1). How to close: count requests for search from support and sales, and ask existing customers how they find past meetings today.
- How users find past meetings today is not stated. How to close: user interviews, with customer names removed.
- Which plan levels the prospect's departments use, and how many users are on each, is not stated (U-1). How to close: the Sales Lead and the PM check the prospect's plan mix.
- No anecdote provider: nothing from customers is captured as a record. How to close: capture interview notes as anecdote records once an anecdote provider is configured.

## 7. Goals and non-goals

Goals:

- Help users find past meetings (P-1, S-1).
- Meet the prospect's request for search (R-1), in a way the plan-level decision allows (Q-1).

Non-goals:

- Deciding plan-level availability in this PRD. That belongs to leadership (Q-1, A-1).
- Pricing and packaging changes beyond what leadership decides (R-3).
- Anything beyond finding past meetings in this PRD.

## 8. Success metrics

- **MET-001** Primary metric: share of search sessions where the user opens a past meeting from the results.
  - Target: proposed: a majority of search sessions end with a past meeting opened. This is a proposal, not stated in the notes.
  - Timeframe: proposed: within 90 days after launch.
  - Baseline: unknown, to be measured before launch. The notes give no search or usage data.
  - Instrumentation: log each search and whether a result is opened.
- **MET-002** Guardrail: outcome of the deal with the large prospect (R-1, M-1).
  - Target: proposed: the prospect gets an answer by its deadline (M-2).
  - Timeframe: proposed: end of week, as the prospect requested (M-2).
  - Baseline: the deal is pending and worth $200K annually (M-1).
- **MET-003** Guardrail: Enterprise upgrades after launch, which the Product Marketing Lead wants to protect (R-3, DIS-1).
  - Target: proposed: no drop from the level before launch.
  - Timeframe: proposed: reviewed quarterly after launch.
  - Baseline: unknown, to be measured before launch.

Vanity check: the number of searches alone is a vanity measure, so MET-001 counts searches that end in an opened meeting. It has no baseline yet.

## 9. Value tests

### User Value / Trust Test

Users gain if they can find a past meeting faster (P-1). Trust depends on search returning the meetings the user expects. Verdict: not yet shown. The user need rests on thin evidence (6c).

### Business Value Test

A $200K annual deal depends on search being offered to the prospect (M-1, R-1), and the Product Marketing Lead sees search as a lever for Enterprise positioning (R-3). The two views pull in opposite directions on plan levels (DIS-1). No cost or effort estimate is in the notes. Verdict: unresolved until leadership decides plan levels (Q-1).

## 10. Solution overview

Direction: a search feature for past meetings (S-1). Plan-level availability is not decided. One option is Enterprise only first, proposed by the PM to keep it simple and give a reason to upgrade (S-2). The other is all plans, which the Sales Lead says was promised to the prospect (R-2). This PRD does not choose between them (DIS-1, Q-1). The notes do not describe screens, so interface detail is left to Stage 2.

## 11. User flow

Assumption: the flow below is a proposal derived from S-1, not stated in the notes.

1. The user enters what they remember about a past meeting. The system searches the user's past meetings.
2. The system shows the matching meetings.
3. The user opens one. The system shows that meeting.

Which users can start this flow depends on the plan-level decision (Q-1).

## 12. Requirements

| REQ-ID | Description | Priority | Acceptance criteria |
|--------|-------------|----------|---------------------|
| REQ-001 | Search past meetings (S-1, P-1) | Must | Given a user who has past meetings and has access to search, When they enter a search, Then the system shows the matching past meetings |
| REQ-002 | Tell the user when nothing matches (S-1) | Must | Given a user with access to search, When their search matches no past meeting, Then the system says nothing was found |
| REQ-003 | Offer search only to the plan levels leadership decides on (Q-1, DIS-1) | Must | Given a leadership decision on plan levels, When a user on a plan level outside that decision opens the product, Then search is not offered to them |
| REQ-004 | Keep plan-level availability changeable without a rebuild (DIS-1, Q-1) | Should | Given search launched for one set of plan levels, When leadership changes the set, Then access follows the new set without rebuilding the feature |
| REQ-005 | Record whether a search ends in an opened meeting (S-1) | Should | Given a search, When the user opens a result or leaves, Then the system records which happened |

## 13. MVP scope

### In v1

- Searching past meetings (S-1).
- A way to limit search by plan level once leadership decides (Q-1).

### Out of v1

- Any plan-level choice made in this PRD (Q-1).
- Pricing, packaging and upsell changes (R-3).
- Anything not about finding past meetings.

## 14. Dependencies and assumptions

- A leadership decision on plan levels, which blocks the scope of v1 (Q-1, A-1).
- Assumption: search across plan boundaries is more complex to build than Enterprise only, as the PM said (S-2). The notes give no estimate.
- The prospect's requirement is as the Sales Lead describes it (R-2).

## 15. Risks and mitigations

- Conflicting requirements: all plans keeps the prospect, Enterprise only supports the upsell story (DIS-1). Mitigation: leadership decides before build starts (A-1), and REQ-004 keeps either outcome possible.
- The deal is lost if search is restricted to Enterprise, in the Sales Lead's view (R-2, M-1). Mitigation: leadership weighs this against upsell before it decides.
- Upsell momentum is lost if search is on all plans, in the Product Marketing Lead's view (R-3). Mitigation: track MET-003 after launch.
- The prospect's deadline is end of week and leadership has not yet decided (M-2, Q-1). Mitigation: escalate now, as the PM said (A-1).
- The evidence is notes-only and unverified until provider data exists (6c). Mitigation: close the gaps in 6c before launch.

## 16. Launch and rollout

The notes give no rollout plan and no date. Launch scope cannot be set until leadership decides which plan levels get search (Q-1). The prospect needs an answer by end of week (M-2). Proposed: leadership decides first (A-1), then Engineering and GTM agree phasing and communication, including how the Sales Lead answers the prospect.

## 17. Open questions

- Which plan levels get search at launch: all plans or Enterprise only? The PM is not committing to either approach and wants leadership to decide (Q-1, DIS-1). Owner: Product leadership (the decision maker is not named in the notes, only leadership).
- What exactly was promised to the prospect (R-2)? Owner: Sales Lead.
- How do users find past meetings today? Owner: PM.
- How much harder is search across plan levels than Enterprise only (S-2)? Owner: PM, who raised the complexity.

## 18. Alignment

- Eng: not named in the notes; to be confirmed before Stage 2.
- Design: not named in the notes; to be confirmed before Stage 2.
- Data: not named in the notes; to be confirmed (6c).
- GTM: Product Marketing Lead signs off on positioning once plan levels are decided (R-3). Sales Lead signs off on what is told to the prospect (R-2).
- Leadership: decides the plan levels (Q-1, A-1). Not aligned yet.

## 19. Decision log

Meeting decisions:

- None. The extraction records no decisions. The PM did not commit to either approach (Q-1).
- Action: document the conflict and get leadership to decide (A-1).

Workflow decisions:

- PB-1 is the primary problem because it is the only problem in the framing, and no problems are parked.
- The plan-level disagreement (DIS-1) is kept open and is not resolved in this PRD.
- Section 8 targets are proposals because the notes state none.
- No evidence or anecdote provider is configured for this run, so evidence comes only from the meeting (6c).

## 20. Traceability

| REQ | Screens | Jira |
|-----|---------|------|
| REQ-001 | not yet created (Stage 2) | not yet created (Stage 3) |
| REQ-002 | not yet created (Stage 2) | not yet created (Stage 3) |
| REQ-003 | not yet created (Stage 2) | not yet created (Stage 3) |
| REQ-004 | not yet created (Stage 2) | not yet created (Stage 3) |
| REQ-005 | not yet created (Stage 2) | not yet created (Stage 3) |
