---
run_id: "2026-01-15-ai-clear-fit"
problems:
  - id: PB-1
    title: Free-form meeting requests are parsed by hand, which is slow and costly
    validation_status: VALIDATED
    missing_evidence: []
    source_items:
      - P-1
      - P-2
      - M-1
      - M-2
      - M-3
      - M-7
    reframed_from_solution: false
primary_problem: PB-1
parked_problems: []
ai:
  proposed: true
  gates:
    "1":
      result: pass
      reason: "Requests are free-form emailed text (P-1) with about 30 distinct constraint types (M-5); the Engineer Lead calls parsing them NLU work (S-1)."
    "2":
      result: pass
      reason: "Parsing free-form text into structured constraints (S-1) with an LLM-based parser (S-2) fits NLU/NLG."
    "3":
      result: pass
      reason: "1300 labeled examples of free-form request to structured output (M-4), and the Data Analyst says there is enough for a proper train/test split (R-2). Spread over about 30 constraint types (M-5); per-type counts, data quality and production access were not discussed."
    "4":
      result: pass
      reason: "The risk is a misparsed constraint (P-3), but every parsed request goes to a human for review (R-1) and low-confidence parses are flagged (S-3)."
    "5":
      result: pass
      reason: "Against 1000 hours per month of manual work (M-3), the hidden costs were named: monitoring drift (R-3), ongoing evals and retraining (R-4), and monthly retraining (S-3). No build cost figure was stated."
  pattern: nlu_nlg
  red_flags: []
  verdict: AI_JUSTIFIED
---

## Problem statement

Meeting requests arrive as free-form emailed text and the team manually parses each one into the system, taking 2 hours per request (lines 10, 14). Customers wait 24-48 hours for confirmation (line 24).

## Who has it

One of the largest customers, a legal firm with complex scheduling rules, sent 500 meeting requests last month (line 8). Requests from other customers are also in the logs (line 16). The internal team doing the manual parsing bears the cost (line 14).

## Exact scenario

A customer emails a request in free-form text, for example: "I need to meet with the client team next week, mornings only, no Wednesdays, preferably in person but video is okay if travel is booked." (line 10). The team manually parses it into structured scheduling constraints in the system (lines 12, 14).

## Current workaround

The team parses each request by hand into the system, at 2 hours per request (line 14).

## Why now

The notes do not state a deadline or trigger. They give the scale: 500 requests last month from one customer, which the VP Product puts at 1000 hours per month of manual work (lines 8, 14).

## Strategic fit

The VP Product expects savings in operational cost and faster request fulfillment for customers (line 22). The Customer Success Manager says it would free the team to focus on complex cases and customer relationships (line 40).

## Validation status

VALIDATED. The notes give figures: 500 requests last month (line 8), 2 hours per request and 1000 hours per month of manual work (line 14), and 24-48 hours of customer wait time (line 24).

## AI decision

**Pattern**: NLU/NLG (parsing free-form natural language into structured constraints).

**Verdict: AI_JUSTIFIED.** All five gates pass and no red flag applies.

- Gate 1 (genuinely probabilistic): pass. Free-form text with about 30 distinct constraint types (P-1, M-5, S-1).
- Gate 2 (matches an AI pattern): pass. NLU (S-1, S-2).
- Gate 3 (data ready): pass. 1300 labeled examples, and the Data Analyst says there is enough for a proper train/test split (M-4, R-2). Spread over about 30 constraint types (M-5); per-type counts, data quality and production access were not discussed.
- Gate 4 (error tolerance): pass. A misparse would schedule a meeting wrong (P-3), but every parsed request goes to a human for review and low-confidence parses are flagged (R-1, S-3).
- Gate 5 (ROI after hidden costs): pass. Monitoring drift, ongoing evals and retraining were named (R-3, R-4, S-3) against 1000 hours per month of manual work (M-3). No build cost figure was stated.

**Next step**: the Engineer Lead proposed to spec the architecture: a fine-tuned model on the request data, a confidence threshold so low-confidence parses get human review, and monthly retraining (line 36). The Data Analyst says an MVP could be running in 4 weeks (line 38).

## Other topics parked

None.
