---
run_id: "2026-01-15-thin-evidence"
problems:
  - id: PB-1
    title: The meeting creation flow may be confusing and slow
    validation_status: UNVALIDATED
    missing_evidence:
      - Whether customers complain about the flow
      - Testing with real users
      - How much time a shorter flow would save
      - How many users change the attendees or description after creating a meeting
    source_items:
      - P-1
      - P-2
      - P-3
      - M-1
      - Q-1
      - Q-2
      - Q-3
      - Q-4
    reframed_from_solution: false
primary_problem: PB-1
parked_problems: []
ai:
  proposed: false
---

## Problem statement

The Designer thinks the meeting creation flow is confusing, with too many steps (line 8), and feels it is slow because of the mental load of clicking through a dialog (lines 16, 20). This is one person's observation and has not been checked against any user data.

## Who has it

Users who create meetings. The only evidence is the Designer's own daily use of the app (lines 8, 24). The Designer is pretty sure users feel the same way (line 30), but has not asked them (line 16).

## Exact scenario

To create a meeting the Designer clicks through title, description, attendees, time and then confirm, which is five steps. Most of the time only the attendees and time are wanted (line 12).

## Current workaround

The notes do not state a workaround.

## Why now

The notes do not state a trigger or deadline. The Product Lead wants to gather data before any redesign (line 28).

## Strategic fit

The notes do not state a strategic link.

## Validation status

UNVALIDATED. The evidence is the Designer's own observation (line 24). Missing evidence:

- Whether customers complain about the flow: not asked (lines 14, 16).
- Testing with real users: none done (lines 22, 24).
- How much time a shorter flow would save: the Designer does not know, "maybe a few seconds" (lines 18, 20).
- How many users change the attendees or description after creating a meeting, which would show whether anyone cares about the order (line 26).

The group agreed to add analytics this sprint and revisit next month (line 32).

## Other topics parked

None.
