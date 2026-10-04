## 1. Header

- Title: Make the notification bell easier to notice
- Owner: Product Manager
- Status: Draft for Human Gate A
- Version: 0.1
- Run ID: 2026-01-15-messy-transcript
- Problem framing: 02-problem.md (primary problem PB-1; PB-2 and PB-3 parked)

## 2. TL;DR

Users miss meeting updates because the notification bell blends into the UI (P-1), and only 12% of users have notifications enabled (M-2). The proposed direction is to redesign the notification UI with a more central bell and an unread count indicator (S-1, S-2). The proposed primary success metric is how many first-time test users miss the bell, which was 6 of 8 in the Designer's user tests (M-1).

## 3. Problem statement

Users are missing meeting updates because the notification bell blends into the UI (P-1). In the Designer's user tests, 6 of 8 missed the bell initially (M-1). Analytics show only 12% of users have notifications enabled, which the Engineer Lead summarised as both a discovery and an adoption problem (P-2, M-2). Validation status: VALIDATED in the problem framing (PB-1). The notes do not say how many users in total are affected and do not state a current workaround.

## 4. Why now and strategic fit

- The notes state no deadline or trigger. The evidence raised in the meeting is the user test result and the low share of users with notifications enabled (M-1, M-2).
- The group decided to add the notification redesign to the backlog (D-1). It is not placed on the roadmap in the notes.
- The notes give no wider strategy statement, and no strategic link is stated.

## 5. Target users and segments

For: users who miss meeting updates (U-1).

Not for: evening users who might want dark mode (U-2) and users of the reporting dashboards (U-3). Those belong to the parked problems PB-3 and PB-2.

## 6. Evidence

### 6a. Data insights

No data provider configured. The figures below were reported verbally in the meeting. They are not verified by a data provider and have no evidence card.

- User tests: 8 participants, 6 of them missed the bell initially; the Designer says this is about 75% (M-1). The sample is small.
- Analytics: only 12% of users have notifications enabled (M-2).

### 6b. Customer anecdotes

No anecdote provider configured. No anecdote records exist for this run.

- No customer quote or interview is captured in the notes for this problem. Frequency is unknown.
- No counter-anecdote was raised in the notes.

### 6c. Evidence gaps

- No data provider: the 12% figure (M-2) comes from a verbal report. How to close: re-run the analytics query once a data connector exists (M3) and attach the result as an evidence card.
- The user test result (M-1) comes from a small sample and is reported verbally. How to close: the Designer shares the test notes, and the test is repeated with more participants.
- The total number of affected users is not stated. How to close: the Data Analyst counts users with an unread meeting update who have not opened it.
- Why only 12% have notifications enabled (P-2) is not explained. How to close: the Data Analyst checks where in the product users enable notifications and how many reach that step.

## 7. Goals and non-goals

Goals:

- Make the notification bell easier to notice for users who miss meeting updates (P-1, S-1).
- Show unread notifications at a glance (S-1, S-2).

Non-goals:

- Fixing slow analytics queries (PB-2, P-3). Parked.
- Dark mode (PB-3, S-4). Kept in the ideas backlog, not the roadmap (D-3).
- Any work on the API outage mentioned in the meeting (Q-2).
- Raising the share of users who enable notifications, beyond what the redesign changes (P-2).

## 8. Success metrics

- **MET-001** Primary metric: share of first-time test users who miss the bell.
  - Target: proposed: at most 1 in 8 test users miss the bell. This is a proposal, not stated in the notes.
  - Timeframe: proposed: measured in a repeat user test before launch.
  - Baseline: 6 of 8 test users missed the bell initially, about 75% (M-1). Re-measure with the same test method.
  - Instrumentation: repeat the Designer's user test with the redesigned UI.
- **MET-002** Guardrail: share of users with notifications enabled.
  - Target: proposed: must not fall below the current level.
  - Timeframe: proposed: reviewed monthly after launch.
  - Baseline: 12% of users have notifications enabled (M-2).
  - Instrumentation: the same analytics that produced the 12% figure.

Vanity check: the share of users with notifications enabled (M-2) is a better adoption outcome than a click count, but it needs an agreed target, so it is a guardrail here. A user test with 8 participants is a weak sample.

## 9. Value tests

### User Value / Trust Test

Users gain because they stop missing meeting updates (P-1). Trust depends on the unread indicator being accurate, so the count must match the notifications the user actually has (S-1, S-2). Verdict: passes on the notes' evidence, subject to the gaps in 6c.

### Business Value Test

The notes state no business value, revenue figure or cost estimate for this work, and no effort estimate. The group only agreed to add it to the backlog (D-1). Verdict: not yet shown. A business case needs the number of affected users (6c).

## 10. Solution overview

Direction: redesign the notification UI by moving the bell more central, adding a colour indicator for the unread count (S-1) and a badge counter (S-2). The notes give no effort estimate. The notes do not describe screens, so interface detail is left to Stage 2.

## 11. User flow

Assumption: the flow below is a proposal derived from S-1 and S-2, not stated in the notes.

1. A meeting update arrives for a user. The system adds it to the unread notifications.
2. The user opens the product. The bell is easy to see and shows an unread count.
3. The user opens the bell and reads the update. The unread count goes down.

## 12. Requirements

| REQ-ID | Description | Priority | Acceptance criteria |
|--------|-------------|----------|---------------------|
| REQ-001 | Place the notification bell in a more central position (S-1) | Must | Given a user with the product open, When the page loads, Then the bell is shown in the new central position |
| REQ-002 | Show a colour indicator for unread notifications (S-1) | Must | Given a user with unread notifications, When the page loads, Then the bell shows the unread colour indicator |
| REQ-003 | Show a badge counter with the number of unread notifications (S-2) | Should | Given a user with unread notifications, When the page loads, Then the badge shows the number of unread notifications |
| REQ-004 | Hide the indicator and badge when nothing is unread (S-1, S-2) | Should | Given a user with no unread notifications, When the page loads, Then no colour indicator and no badge counter are shown |
| REQ-005 | Repeat the user test with the redesigned bell (M-1) | Could | Given the redesigned bell, When the user test is repeated with new participants, Then the number who miss the bell initially is recorded |

## 13. MVP scope

### In v1

- Moving the bell to a more central position (S-1).
- A colour indicator for the unread count (S-1).
- A badge counter (S-2).

### Out of v1

- Slow analytics queries and the schema repartitioning (PB-2, S-3).
- Dark mode, including the Designer's off-roadmap prototype (PB-3, S-4, D-4).
- Anything about the API outage (Q-2).
- Changes to how users enable notifications beyond the redesign.

## 14. Dependencies and assumptions

- Assumption: a more visible bell and an unread count will lead users to notice meeting updates. The notes do not test this (S-1, S-2).
- Assumption: the unread count can be computed for each user. The notes do not say.
- A repeat user test needs participants and the Designer's test method (M-1).

## 15. Risks and mitigations

- The redesign may not raise the share of users with notifications enabled, since the low share was named as an adoption problem as well as a discovery problem (P-2). Mitigation: track MET-002 and check the gap in 6c on why so few enable them.
- The user test sample is small (M-1). Mitigation: repeat it with more participants (REQ-005).
- The evidence is notes-only and unverified until provider data exists: both figures were only spoken in the meeting (M-1, M-2). Mitigation: close the gaps listed in 6c before launch and re-measure the baseline.
- No effort estimate exists, so timing is unknown. Mitigation: ask Engineering for an estimate before the work is scheduled.

## 16. Launch and rollout

The group decided only to add the redesign to the backlog (D-1). The notes give no rollout plan and no date. Proposed: decide phasing with Engineering after an estimate exists. Communication plan to be agreed with GTM.

## 17. Open questions

- How many users in total miss meeting updates? Owner: Data Analyst.
- Why do only 12% of users have notifications enabled (M-2)? Owner: Data Analyst.
- What is the effort for the redesign? Owner: Engineer Lead.
- When is the redesign scheduled, given it is only in the backlog (D-1)? Owner: Engineer Lead.
- Parked, not for this PRD: the slow analytics queries (PB-2) and how many customers want dark mode (PB-3, Q-1). Owners: Data Analyst and Designer.

## 18. Alignment

- Eng: Engineer Lead signs off on feasibility and the estimate.
- Design: Designer signs off on the bell and badge design (S-1, S-2).
- Data: Data Analyst owns the notification analytics and any re-measurement (M-2).
- GTM: a GTM owner is not named in the notes; to be confirmed before launch.
- Leadership: not named in the notes; to be confirmed.

## 19. Decision log

Meeting decisions:

- Add the notification redesign to the backlog (D-1).
- Add the schema repartitioning to the backlog and schedule planning later (D-2). Not part of this PRD.
- Keep dark mode in the ideas backlog, not the roadmap (D-3).
- The Designer may prototype dark mode off the roadmap (D-4). Not part of this PRD.

Workflow decisions:

- PB-1 is the primary problem because it is the one backed by user test evidence (M-1); PB-2 and PB-3 are parked, as in the problem framing.
- Section 8 targets are proposals because the notes state none.
- No evidence or anecdote provider exists in this milestone, so evidence comes only from the meeting (6c).

## 20. Traceability

| REQ | Screens | Jira |
|-----|---------|------|
| REQ-001 | not yet created (Stage 2) | not yet created (Stage 3) |
| REQ-002 | not yet created (Stage 2) | not yet created (Stage 3) |
| REQ-003 | not yet created (Stage 2) | not yet created (Stage 3) |
| REQ-004 | not yet created (Stage 2) | not yet created (Stage 3) |
| REQ-005 | not yet created (Stage 2) | not yet created (Stage 3) |
