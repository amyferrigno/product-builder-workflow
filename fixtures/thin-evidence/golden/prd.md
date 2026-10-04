## 1. Header

- Title: Meeting creation flow, validate before redesign
- Owner: Product Lead
- Status: Draft for Human Gate A
- Version: 0.1
- Run ID: 2026-01-15-thin-evidence
- Problem framing: 02-problem.md (primary problem PB-1, UNVALIDATED)

## 2. TL;DR

The Designer thinks the meeting creation flow is confusing and slow, with too many steps (P-1, P-3), but this is one person's observation and is UNVALIDATED. The direction is to collect usage data first, then decide on a quick mode and full mode (S-2, S-1, D-1). The proposed primary success metric is the number of steps to create a meeting with only attendees and time, currently five (M-1).

## 3. Problem statement

To create a meeting the Designer clicks through title, description, attendees, time and then confirm, which is five steps. Most of the time only the attendees and time are wanted (P-2, M-1). The Designer feels the flow is slow because of the mental load of clicking through a dialog (P-3). Validation status: UNVALIDATED (PB-1). The only evidence is the Designer's own daily use of the app (U-1). Customers have not been asked (Q-1), the flow has not been tested with real users (Q-3), and the time a shorter flow would save is a guess, "maybe a few seconds" (M-2, Q-2).

## 4. Why now and strategic fit

The notes state no trigger, deadline or strategic link. The group decided to gather some data before redesigning (D-1) and to add some analytics this sprint and revisit next month (D-2). Strategic fit cannot be assessed from the notes.

## 5. Target users and segments

For: users who create meetings (U-1). Who exactly, and how many, is not known.

Not for: no group is excluded in the notes. Nothing is known about users who rarely change the attendees or description (Q-4).

## 6. Evidence

### 6a. Data insights

No data provider configured. No evidence cards exist for this run. The only figure in the notes is that the current flow has five steps (M-1), which describes the product, not user behaviour.

### 6b. Customer anecdotes

No anecdote provider configured. No anecdote records exist for this run, and no customer has been asked (Q-1). The only account is the Designer's own use of the app (U-1), which is an internal observation, not a customer anecdote. No counter-anecdote exists.

### 6c. Evidence gaps

- Whether customers complain about the flow (Q-1). How to close: ask customers or review support feedback about meeting creation.
- Whether the flow holds up with real users (Q-3). How to close: test the current flow with real users.
- How much time a shorter flow would save (Q-2, M-2). How to close: measure time to create a meeting from usage data.
- How many users change the attendees or description after creating a meeting (Q-4). How to close: the analytics the group decided to add this sprint (S-2, D-2).
- No data provider or anecdote provider is configured. How to close: add data enrichment and anecdotes when available.

## 7. Goals and non-goals

Goals:

- Find out whether the meeting creation flow is a real problem for users (Q-1, Q-3).
- Measure how often users change attendees or description after creating a meeting (Q-4).
- Decide on a quick mode and full mode only after the data is in (D-1, S-1).

Non-goals:

- Redesigning the flow before data is gathered (D-1).
- Claiming a time saving that has not been measured (Q-2).

## 8. Success metrics

- **MET-001** Primary metric: steps needed to create a meeting with only attendees and time.
  - Target: proposed: two steps through a quick mode (S-1). This is a proposal, and it applies only if the analytics support a redesign.
  - Timeframe: proposed: measured after a quick mode launches, at the revisit following the analytics review (D-2).
  - Baseline: five steps today (M-1).
  - Instrumentation: count steps in the creation dialog from the new analytics (S-2).
- **MET-002** Guardrail: share of users who change attendees or description after creating a meeting.
  - Target: proposed: must not rise after a redesign.
  - Timeframe: proposed: monitored from the analytics launch onward.
  - Baseline: unknown, to be measured before launch (Q-4).
- **MET-003** Guardrail: time to create a meeting.
  - Target: proposed: must not get slower.
  - Timeframe: proposed: monitored from the analytics launch onward.
  - Baseline: unknown, to be measured before launch. The only figure is a guess, "maybe a few seconds" saved (M-2).

Vanity check: step count is an output measure. It matters only if the analytics show users care about the order (Q-4), so the guardrails carry the outcome signal.

## 9. Value tests

### User Value / Trust Test

Unproven. The Designer believes users feel the same way but has not asked them (Q-1, Q-3). Value is unknown until customers or usage data confirm the flow is a burden. Verdict: not yet passed.

### Business Value Test

Unproven. The notes give no customer impact, revenue link or time saving (Q-2). The only business decision is to gather data first (D-1). Verdict: not yet passed.

## 10. Solution overview

Direction in two phases. Phase one: add analytics this sprint to see how many users change the attendees or description after creating a meeting (S-2, A-1). Phase two, only if the data supports it: a quick mode for just attendees and time, and a full mode for all the details (S-1). The notes do not describe screens.

## 11. User flow

Current flow (P-2): the user enters title, description, attendees and time, then confirms. The system creates the meeting.

Proposed flow, only after the data review (S-1): in quick mode the user enters attendees and time, then confirms, and the system creates the meeting. In full mode the user enters all the details first.

## 12. Requirements

| REQ-ID | Description | Priority | Acceptance criteria |
|--------|-------------|----------|---------------------|
| REQ-001 | Record whether attendees or description change after a meeting is created (S-2, Q-4) | Must | Given a meeting that was just created, When a user edits its attendees or description, Then the edit is recorded with the field that changed |
| REQ-002 | Record the steps and time taken to create a meeting (M-1, Q-2) | Should | Given a user creating a meeting, When they confirm it, Then the number of steps and the time taken are recorded |
| REQ-003 | Offer a quick mode for attendees and time only (S-1) | Could | Given the analytics review supports a redesign, When a user starts a new meeting, Then they can create it with only attendees and time |

## 13. MVP scope

### In v1

- Analytics on changes after meeting creation (S-2, D-2).
- Recording steps and time to create a meeting.

### Out of v1

- Quick mode and full mode, until the data review supports it (D-1, S-1).
- Any redesign of the creation dialog.

## 14. Dependencies and assumptions

- Analytics can be added this sprint (D-2).
- Assumption: enough users create meetings for the analytics to be conclusive. The number of users is not known.
- Assumption: edits after creation are a fair signal of whether the order matters (Q-4).

## 15. Risks and mitigations

- The problem is not real, and a redesign wastes effort. Mitigation: gate any redesign on the data review (D-1).
- The Designer's view is not representative (U-1). Mitigation: ask customers and test with real users (Q-1, Q-3).
- Analytics are too thin to decide. Mitigation: revisit next month and extend the measurement if needed (D-2).
- The time saving is overstated. Mitigation: use only measured time, never the guess (M-2).

## 16. Launch and rollout

Phase one: analytics this sprint, revisit next month (D-2). Phase two: a quick mode behind a feature flag only if the data supports it. Communication is not covered in the notes.

## 17. Open questions

- Are customers complaining about the flow (Q-1)? Owner: Product Lead.
- How much faster would a two-step flow be (Q-2)? Owner: Designer.
- Does this hold up with real users (Q-3)? Owner: Designer.
- How many users change the attendees or description after creating a meeting (Q-4)? Owner: Engineer Lead.

## 18. Alignment

- Eng: Engineer Lead signs off on the analytics (S-2).
- Design: Designer signs off on any quick mode and full mode proposal (S-1).
- Data: owner of analytics review to be confirmed.
- GTM: not involved in the notes; consulted if customers are asked (Q-1).
- Leadership: Product Lead decides whether to proceed after the data review (D-1).

## 19. Decision log

Meeting decisions:

- Gather some data before redesigning (D-1).
- Add some analytics this sprint and revisit next month (D-2).

Workflow decisions:

- PB-1 is the primary problem because it is the only problem in the framing, and no problems are parked.
- The problem stays UNVALIDATED, so the PRD scopes phase one to measurement and gates the redesign.
- Section 8 targets are proposals because the notes state none.

## 20. Traceability

| REQ | Screens | Jira |
|-----|---------|------|
| REQ-001 | not yet created (Stage 2) | not yet created (Stage 3) |
| REQ-002 | not yet created (Stage 2) | not yet created (Stage 3) |
| REQ-003 | not yet created (Stage 2) | not yet created (Stage 3) |
