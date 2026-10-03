# Flows

## FLOW-001 Review a parsed request
**REQs**: REQ-001, REQ-002, REQ-003, REQ-004

```mermaid
flowchart TD
  A[Review queue] --> B[Open a request]
  B --> C[Compare original text with parsed draft]
  C -->|Correct| D[Approve draft]
  C -->|Wrong| E[Edit constraints, then approve]
  C -->|Unsure| F[Parse again]
  F --> C
  D --> G[Meeting scheduled]
  E --> G
```

## FLOW-002 Parser fails or cannot read a request
**REQs**: REQ-003, REQ-008

```mermaid
flowchart TD
  A[Request arrives] --> B{Parser works and request readable?}
  B -->|Yes| C[Review queue]
  B -->|No| D[Manual queue]
  D --> E[Person parses by hand]
  E --> F[Reviewer approves]
  F --> G[Meeting scheduled]
```

## FLOW-003 Check parser quality
**REQs**: REQ-005, REQ-006

```mermaid
flowchart TD
  A[Parser quality] --> B[Run accuracy check on held-out examples]
  B --> C{All thresholds met?}
  C -->|Yes| D[Launch can go ahead]
  C -->|No| E[Ask the Engineer Lead]
```
