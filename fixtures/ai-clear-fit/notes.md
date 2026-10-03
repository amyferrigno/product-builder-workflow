# Customer Success Team Meeting - Oct 3, 2026

## Attendees
VP Product, Customer Success Manager, Engineer Lead, Data Analyst

---

VP Product: One of our largest customers sent us 500 meeting requests last month. They're a legal firm with complex scheduling rules.

Customer Success Manager: Exactly. The requests come as emails with free-form text like "I need to meet with the client team next week, mornings only, no Wednesdays, preferably in person but video is okay if travel is booked."

Engineer Lead: That sounds like NLU work. Parsing that into structured scheduling constraints.

VP Product: Right. Right now our team is spending 2 hours per request manually parsing that into our system. For 500 requests, that's 1000 hours per month of manual work.

Data Analyst: We have logs of those 500 requests plus another 800 from other customers. That's 1300 labeled examples of freeform request to structured output.

Engineer Lead: How many request types are there?

Data Analyst: About 30 distinct constraint types: date ranges, time ranges, day-of-week exclusions, location preferences, attendee constraints, and a few others.

VP Product: If we could automate 80% of that parsing with an LLM-based parser, we'd save huge amounts of operational cost. And customers would see faster request fulfillment.

Customer Success Manager: That would be game-changing. Right now customers wait 24-48 hours for confirmation. With automation, we could confirm in minutes.

Engineer Lead: The risk is errors. If the AI misparses a constraint, the meeting gets scheduled wrong.

VP Product: That's acceptable because every parsed request still goes to a human for review. The AI is a draft, not final.

Data Analyst: We could measure parser accuracy on a holdout set. We have enough data to do proper train/test split.

Engineer Lead: And we'd need to monitor drift over time as request patterns evolve.

VP Product: Absolutely. This is not a one-time model. We'd need ongoing evals and retraining.

Engineer Lead: Okay, I'm convinced this could work. Let's spec the architecture: a fine-tuned model on our request data, a confidence threshold so low-confidence parses get human review, and monthly retraining on new labeled data.

Data Analyst: We could have an MVP running in 4 weeks.

Customer Success Manager: That would free up our team to focus on complex cases and customer relationships.
