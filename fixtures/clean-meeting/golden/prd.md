## 1. Header

- Title: Faster meeting scheduling
- Owner: Product Manager
- Status: Draft for Human Gate A
- Version: 0.1
- Run ID: 2026-01-15-clean-meeting
- Problem framing: 02-problem.md (primary problem PB-1)

## 2. TL;DR

Finding a meeting time is slow and fragmented: customers check multiple calendars and send back-and-forth emails, and say they spend 20+ minutes per meeting (P-1, P-2, M-2). The proposed direction is to integrate with the Google and Outlook calendars and show available time (S-1). The proposed primary success metric is the number of back-and-forth messages per scheduled meeting, which the logs put at 3-4 today (M-3).

## 3. Problem statement

Customers who schedule meetings check multiple calendars and send back-and-forth emails to find a time (P-2). Copy-paste calendar links do not auto-update if the host's availability changes (P-3). Their calendar setups differ: some use Google Calendar, some Outlook, some both (U-1). Validation status: VALIDATED in the problem framing (PB-1). Of 200 Q3 support tickets analysed, 45 (about 22%) were complaints about how long it takes to find a time (M-1). Five customer interviews last month all reported wasting time on calendar hunting (M-4).

## 4. Why now and strategic fit

- A large deal that has not signed yet said "make scheduling frictionless or we're going elsewhere" (R-1).
- Churn analysis shows scheduling frustration is a leading indicator of churn in months 2-3 of onboarding (M-6).
- Three of the five interviewed customers said they are looking at competitors for this feature (M-5).
- The group decided to scope this for the Q4 roadmap (D-1). The notes give no wider strategy statement beyond that.

## 5. Target users and segments

For: customers whose calendar setups differ, using Google Calendar, Outlook or both (U-1). Enterprise accounts are included, and their IT must approve calendar integrations (U-2, R-2).

Not for: needs outside scheduling, such as calendar sync or other integrations (D-2).

## 6. Evidence

### 6a. Data insights

No data provider configured. The figures below were reported verbally in the meeting. They are not verified by a data provider and have no evidence card.

- 200 support tickets analysed from Q3; 45 of them (about 22%) were complaints about how long it takes to find a time (M-1).
- 3-4 back-and-forth messages per scheduled meeting, seen in the logs (M-3).
- Customers say they spend 20+ minutes per meeting (M-2). This is self-reported.
- Churn analysis: scheduling frustration is a leading indicator of churn in months 2-3 of onboarding (M-6).

### 6b. Customer anecdotes

No anecdote provider configured. No anecdote records exist for this run.

- Five customer interviews last month; all five said they waste time on calendar hunting, and three said they are looking at competitors for this feature (M-4, M-5). The interviews are reported in the meeting only, and no verbatim interview quote is captured.
- A large deal that has not signed yet said "make scheduling frictionless or we're going elsewhere" (R-1). Frequency is unknown.
- No counter-anecdote was raised in the notes.

### 6c. Evidence gaps

- No data provider: the ticket and log figures (M-1, M-3) come from a verbal report. How to close: re-run the ticket analysis and the log count once a data connector exists (M3), and attach the results as evidence cards.
- No anecdote provider: interview findings (M-4, M-5) are not captured as records. How to close: capture the interview notes as anecdote records once the anecdote step exists (M4), with customer names removed.
- Time spent per meeting is self-reported (M-2). How to close: measure time from first message to confirmed invite from the logs.
- The link between scheduling frustration and churn (M-6) has no stated size. How to close: ask for the churn analysis figures and cohort.
- The status of the large deal (R-1) is not documented beyond the quote. How to close: the Support Lead confirms the deal timing and what was promised.

## 7. Goals and non-goals

Goals:

- Reduce the time customers spend finding a meeting time (P-1, M-2).
- Reduce the back-and-forth messages needed to schedule a meeting (P-2, M-3).
- Work for customers on Google Calendar, Outlook or both (S-1, U-1).

Non-goals:

- Calendar sync (D-2).
- Other integrations beyond Google and Outlook calendars for scheduling (D-2).
- Anything beyond finding a meeting time in this PRD.

## 8. Success metrics

- **MET-001** Primary metric: back-and-forth messages per scheduled meeting.
  - Target: proposed: at most one back-and-forth message per scheduled meeting. This is a proposal, not stated in the notes.
  - Timeframe: proposed: within 90 days after launch.
  - Baseline: 3-4 back-and-forth messages per scheduled meeting, from the logs (M-3). Re-measure before launch.
  - Instrumentation: count messages per scheduled meeting from the same logs.
- **MET-002** Guardrail: share of support tickets complaining about time to find a meeting time.
  - Target: proposed: must not rise above the Q3 level.
  - Timeframe: proposed: reviewed monthly after launch.
  - Baseline: 45 of 200 Q3 tickets, about 22% (M-1).
- **MET-003** Guardrail: enterprise accounts are not blocked by IT approval of calendar integrations (U-2, R-2).
  - Target: proposed: no enterprise account stalls on IT approval for this feature.
  - Timeframe: proposed: first enterprise accounts after launch.
  - Baseline: unknown, to be measured before launch.

Vanity check: messages per meeting is a proxy for effort. Time to schedule (M-2) is a better outcome measure but has no instrumentation yet.

## 9. Value tests

### User Value / Trust Test

Customers gain because they stop hunting across calendars and email threads (P-2, M-4). Trust depends on the available time being correct, so the system must show time that reflects the customer's real calendars, which copy-paste links do not do when availability changes (P-3). Setups differ, so both Google and Outlook must work (U-1). Verdict: passes on the notes' evidence, subject to the gaps in 6c.

### Business Value Test

A large unsigned deal depends on frictionless scheduling (R-1), scheduling frustration predicts early churn (M-6), and customers say they are looking at competitors (M-5). The cost is the Engineer Lead's estimate of 8 weeks, the absolute minimum for a good experience (M-7). Verdict: passes, with churn and deal impact still unsized (6c).

## 10. Solution overview

Direction: integrate with the Google and Outlook calendar APIs and show available time (S-1). Scope stays on scheduling, not calendar sync or other integrations (D-2). One flow is prototyped next sprint to reduce API risk (D-3). The notes do not describe screens, so interface detail is left to Stage 2.

## 11. User flow

Assumption: the flow below is a proposal derived from S-1, not stated in the notes.

1. The host connects a Google or Outlook calendar. The system confirms the connection.
2. The host asks to find a meeting time. The system shows available time from the connected calendars.
3. The host shares the chosen options. The invitee picks a time.
4. The system sends the calendar invite and the host receives the confirmation.

## 12. Requirements

| REQ-ID | Description | Priority | Acceptance criteria |
|--------|-------------|----------|---------------------|
| REQ-001 | Connect a Google Calendar account (S-1, U-1) | Must | Given a customer with a Google calendar, When they connect it, Then the system can read their availability |
| REQ-002 | Connect an Outlook calendar account (S-1, U-1) | Must | Given a customer with an Outlook calendar, When they connect it, Then the system can read their availability |
| REQ-003 | Show available time across all connected calendars (S-1, P-2) | Must | Given a customer with both Google and Outlook calendars connected, When they ask for a meeting time, Then the system shows only times free in both |
| REQ-004 | Keep shared availability current (P-3) | Should | Given a host whose availability changed after sharing, When an invitee opens the shared options, Then the options reflect the changed availability |
| REQ-005 | Handle enterprise IT approval of calendar integrations (R-2, U-2) | Must | Given an enterprise account whose IT has not approved the integration, When the customer tries to connect a calendar, Then the system tells them approval is required and does not connect |
| REQ-006 | Record messages per scheduled meeting (M-3) | Should | Given a scheduled meeting, When it is confirmed, Then the number of back-and-forth messages for it is recorded |

## 13. MVP scope

### In v1

- Google Calendar and Outlook calendar connection (S-1).
- Showing available time for scheduling (S-1).
- Enterprise IT approval call-out (R-2).
- One prototyped flow to de-risk the API work (D-3).

### Out of v1

- Calendar sync (D-2).
- Other integrations (D-2).
- Anything not about finding a meeting time.

## 14. Dependencies and assumptions

- Access to the Google and Outlook calendar APIs (S-1).
- Enterprise IT approval of calendar integrations, (R-2, U-2).
- The Engineer Lead's estimate of 8 weeks holds for Google and Outlook (M-7).
- Assumption: the logs can count messages per scheduled meeting (M-3).

## 15. Risks and mitigations

- The large deal is lost if the work takes too long (R-1). Mitigation: scope tightly to scheduling (D-2) and prototype one flow next sprint (D-3).
- API integration work is harder than expected (D-3). Mitigation: the prototype next sprint.
- Enterprise IT approval can block enterprise accounts (U-2). Mitigation: call it out in requirements (R-2) and in REQ-005.
- Setups differ across customers (U-1). Mitigation: support Google, Outlook and both.
- The evidence is notes-only and unverified until provider data exists: the ticket, log and interview figures were only spoken in the meeting, with no evidence cards or anecdote records (M-1, M-3, M-4). Mitigation: close the gaps listed in 6c, with provider data and anecdote records, before launch, and re-measure the baseline.

## 16. Launch and rollout

The group decided to scope this for the Q4 roadmap (D-1). The notes give no rollout plan. Proposed: prototype one flow next sprint (D-3), then decide phasing with Engineering once the prototype result is known. Communication plan to be agreed with GTM.

## 17. Open questions

- What is the current time from first message to confirmed invite? Owner: Engineer Lead.
- What is the size of the churn effect of scheduling frustration (M-6)? Owner: Support Lead.
- When must the large deal's requirement be met (R-1)? Owner: Support Lead.
- Which enterprise IT approval steps apply (R-2)? Owner: Support Lead.

## 18. Alignment

- Eng: Engineer Lead signs off on feasibility and the estimate (M-7).
- Design: a Designer is not named in the notes; to be confirmed before Stage 2.
- Data: owner of the log and ticket analysis to be confirmed (6c).
- GTM: Support Lead signs off on customer and enterprise points (R-2).
- Leadership: PM adds this to the strategy doc (A-1).

## 19. Decision log

Meeting decisions:

- Scope this for the Q4 roadmap (D-1).
- Keep this in scope for scheduling, not calendar sync or other integrations (D-2).
- Prototype one flow next sprint to de-risk the API work (D-3).

Workflow decisions:

- PB-1 is the primary problem because it is the only problem in the framing, and no problems are parked.
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
| REQ-006 | not yet created (Stage 2) | not yet created (Stage 3) |
