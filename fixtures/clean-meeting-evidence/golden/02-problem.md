---
run_id: "2026-01-15-clean-meeting-evidence"
problems:
  - id: PB-1
    title: Finding a meeting time is slow and fragmented
    validation_status: VALIDATED
    missing_evidence: []
    source_items:
      - P-1
      - P-2
      - P-3
      - M-1
      - M-2
      - M-3
      - M-4
      - M-5
      - M-6
    reframed_from_solution: false
primary_problem: PB-1
parked_problems: []
ai:
  proposed: false
---

## Problem statement

Finding a meeting time is slow and fragmented (line 18). Customers check multiple calendars, send back-and-forth emails, and say they spend 20+ minutes per meeting (line 10).

## Who has it

Customers who schedule meetings. Their calendar setups differ: some use Google Calendar, some Outlook, some both (line 22). Enterprise accounts also need their IT to approve calendar integrations, which is slowing their adoption pilots (line 36).

## Exact scenario

A customer needs to find a time for a meeting. They check multiple calendars, send emails with a few options, and refine in back-and-forth emails or chat. The winner sends a calendar invite (lines 10, 20). The logs show 3-4 back-and-forth messages per scheduled meeting (line 12).

## Current workaround

Customers start by emailing a few options, refine in Slack or back-and-forth emails, and the winner sends a calendar invite. Some use copy-paste calendar links, but these do not auto-update if the host's availability changes (line 20).

## Why now

A large deal that has not signed yet said "make scheduling frictionless or we're going elsewhere" (line 26). Churn analysis shows scheduling frustration is a leading indicator of churn in months 2-3 of onboarding (line 26).

## Strategic fit

The group decided to scope this for the Q4 roadmap (line 34) and to keep it in scope for scheduling, not calendar sync or other integrations (line 38). The notes give no wider strategy statement.

## Validation status

VALIDATED. Of 200 Q3 support tickets, 45 (about 22%) were complaints about how long it takes to find a time (line 10). Five customer interviews last month all reported wasting time on calendar hunting, and three said they are looking at competitors for this feature (line 16). The logs show 3-4 back-and-forth messages per scheduled meeting (line 12).

## Other topics parked

Calendar sync and other integrations are explicitly out of scope for this work (line 38).
