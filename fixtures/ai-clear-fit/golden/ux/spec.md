# Screen spec

## SCR-001 Review queue

**Purpose**: The reviewer sees every parsed request waiting for approval, with low-confidence drafts flagged, and the manual queue for requests the parser could not handle.
**REQs**: REQ-002, REQ-003, REQ-008

### Components
- Table of waiting requests with sender, start of the request, flag and Review button
- Filter for all, low confidence only, or manual queue
- Link to parser quality

### Copy
- Title: Review queue
- Intro: Every parsed request waits here until a reviewer approves it. Nothing is scheduled before that.
- Flags: Low confidence: check closely; Draft ready; Sent to manual queue
- Empty: No requests are waiting for review. New emailed requests appear here after they are parsed.
- Error: The queue could not load. Your work is not lost, and no meeting has been scheduled.
- Escalation: If the parser fails, is unavailable, or cannot read a request, the request goes to the manual queue. The customer is not blocked.

### Interactions
- Review opens SCR-002 for that request
- Low-confidence drafts open directly in the low-confidence state of SCR-002
- Send to manual parsing moves the request to the manual queue
- Try again reloads the queue

### Analytics events
- queue_viewed
- queue_filter_applied
- request_opened
- request_sent_to_manual_queue

## SCR-002 Request review

**Purpose**: The reviewer compares the original request with the parsed draft, corrects it if needed and approves it before anything is scheduled.
**REQs**: REQ-001, REQ-002, REQ-003, REQ-004, REQ-008

### Components
- Original request text panel
- Parsed constraints table with a confidence label
- Approve, Edit constraints, Reject, Parse again and Send to manual parsing buttons
- Edit form with one field per constraint
- Explanation of which text produced which constraint

### Copy
- Notice: This is a draft from the parser, not a final answer. Compare it with the original request.
- Low confidence: the parser is unsure about this draft. Check every constraint against the original text before approving.
- Empty: The parser found no scheduling constraints in this text. Nothing was invented.
- Error: The parser failed on this request. No meeting was scheduled.
- Success: Draft approved. Your corrections were recorded so the parser can learn from them.

### Interactions
- Approve is the only way a meeting gets scheduled
- Edit constraints opens the edit form; Save and approve records the correction
- Parse again keeps the current draft and shows a new one for comparison
- Send to manual parsing moves the request to the manual queue
- Reject discards the draft and returns to the queue

### Analytics events
- draft_viewed
- constraint_edited
- draft_approved
- draft_rejected
- parse_again_requested
- sent_to_manual_parsing

## SCR-003 Parser quality

**Purpose**: The team checks accuracy on held-out examples against the launch thresholds, and sees drift and correction rates after launch.
**REQs**: REQ-005, REQ-006

### Components
- Table of dimensions with must-pass threshold and result
- Run the accuracy check button
- Drift and corrections section
- Note for the Engineer Lead

### Copy
- Title: Parser quality
- Intro: Any missed threshold means no launch.
- Empty: The accuracy check has not run yet, so there are no results. Parsing stays behind human review until the thresholds are met.
- Error: The accuracy check failed to complete. No results were saved and the previous results are unchanged.
- Success: The accuracy check finished and every must-pass threshold is met.

### Interactions
- Run the accuracy check starts the check on held-out examples
- Run again keeps the earlier results for comparison
- Ask the Engineer Lead opens the escalation state

### Analytics events
- quality_viewed
- accuracy_check_started
- accuracy_check_failed
- engineer_lead_contacted
