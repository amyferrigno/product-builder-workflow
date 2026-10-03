---
run_id: "2026-01-15-solution-first-chatbot"
problems:
  - id: PB-1
    title: Support may be spending too much effort on repetitive questions
    validation_status: UNVALIDATED
    missing_evidence:
      - Support ticket breakdown by question type
      - Confirmation from the support team of what they spend their time on
      - Evidence of actual customer demand for automated support
      - Cost of support (described as expensive, no figure given)
    source_items:
      - P-1
      - P-2
      - S-1
      - M-1
      - Q-1
      - Q-2
      - Q-3
    reframed_from_solution: true
primary_problem: PB-1
parked_problems: []
ai:
  proposed: true
  gates:
    "1":
      result: unknown
      reason: "The only example questions given are how to reschedule and which calendar systems are supported (R-1). The notes do not say whether answers follow fixed rules or vary (Q-3)."
    "2":
      result: pass
      reason: "The proposal is a chatbot answering natural-language support questions (S-1, R-1), which fits NLU/NLG."
    "3":
      result: unknown
      reason: "Only a guess of maybe a few hundred tickets per month (M-1), which the Engineer Lead called thin for diverse questions (M-2). No breakdown per question type (Q-1)."
    "4":
      result: unknown
      reason: "Error tolerance was not discussed. The proposal is to handle support automatically (S-1) with no mention of human review."
    "5":
      result: unknown
      reason: "Support is called expensive with no figure (P-1), and no build, labelling or monitoring cost was discussed. A prototype by end of Q4 was requested (R-2)."
  pattern: nlu_nlg
  red_flags: []
  verdict: NEEDS_DATA
---

## Problem statement

The VP Product says customer support is expensive and that the support team spends all day on repetitive questions (lines 8, 12). The notes do not show how large this is or which questions dominate. This framing replaces the original proposal, an AI chatbot (line 8), with the underlying problem it was meant to address.

## Who has it

The support team, which the VP Product says answers repetitive questions all day (line 12). The VP Product has not yet talked to support about what they spend time on (lines 14, 16).

## Exact scenario

The notes give no concrete case. The example questions given are how to reschedule a meeting and which calendar systems are supported (line 12).

## Current workaround

The notes do not state a workaround.

## Why now

The VP Product says competition is shipping chatbots and "we need to keep up" (lines 16, 28), and wants a prototype by end of Q4 (line 32). No evidence of urgency in the support workload itself was given. The PM suggested revisiting in two weeks once there are numbers (line 34), and the VP Product agreed (line 36).

## Strategic fit

The VP Product framed it as a question of where to compete: the scheduling tool is table stakes, but customer support is expensive (line 8).

## Validation status

UNVALIDATED. This is a hypothesis that came from a proposed solution. Missing evidence: the support ticket breakdown by question type (lines 22, 24), confirmation from the support team of what they spend time on (lines 14, 16), actual customer demand (line 30), and the cost of support (line 8, no figure given). The only volume figure is a guess of "maybe a few hundred per month" (line 24).

## AI decision

**Pattern**: NLU/NLG (answering natural-language support questions).

**Verdict: NEEDS_DATA.** No gate failed and no red flag is established, but four of the five gates cannot be answered from the notes.

- Gate 1 (genuinely probabilistic): unknown. Example questions are how to reschedule and which calendar systems are supported (R-1); whether the answers follow fixed rules is not discussed.
- Gate 2 (matches an AI pattern): pass. A chatbot answering natural-language support questions (S-1, R-1) fits NLU/NLG.
- Gate 3 (data ready): unknown. Maybe a few hundred tickets per month (M-1), called thin by the Engineer Lead (M-2), with no breakdown per question type (Q-1).
- Gate 4 (error tolerance): unknown. Not discussed.
- Gate 5 (ROI after hidden costs): unknown. No cost figures (P-1).

**Next step**, as agreed in the meeting: the PM gathers the ticket breakdown and checks for customer demand (line 30), and the group revisits in two weeks (line 34).

## Other topics parked

None.
