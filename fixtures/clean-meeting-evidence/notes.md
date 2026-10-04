# Product Team Meeting - Oct 3, 2026

## Attendees
PM, Engineer Lead, Support Lead

---

PM: We've been hearing from customers that scheduling individual meetings is slow. Support lead, you mentioned this in last week's post-mortem.

Support Lead: Yes. We analyzed 200 support tickets from Q3. 45 of them—about 22%—were complaints about how long it takes to find a time. Customers say they're checking multiple calendars, sending back-and-forth emails, and spending 20+ minutes per meeting.

Engineer Lead: I see that too in the logs. Users are creating 3-4 back-and-forth messages per scheduled meeting. That's expensive API calls for us and frustrating for them.

PM: Has anyone talked to customers directly about this?

Support Lead: Yes, I did five customer interviews last month. All five said the same thing: "I'm wasting time on calendar hunting. I just want to send one link and be done." Three of them have said they're looking at competitors for this feature.

PM: Okay, so the problem is clear: finding meeting time is slow and fragmented. Right now what do customers do?

Support Lead: They typically start by emailing a few options, then refinement happens in Slack or back-and-forth emails. The winner sends a calendar invite. Some customers use copy-paste calendar links, but those don't auto-update if the host's availability changes.

Engineer Lead: And we can't help much because each customer's setup is different. Some use Google Calendar, some use Outlook, some use both.

PM: Right. Why is this urgent now?

Support Lead: Two things. First, we're in final stages with a large deal (they haven't signed yet), and they explicitly said "make scheduling frictionless or we're going elsewhere." Second, churn analysis shows scheduling frustration is a leading indicator of churn in months 2-3 of onboarding.

PM: When should we get this done?

Engineer Lead: If we're solving for Google and Outlook calendars, integrating with their APIs, and showing available time, I'd estimate 8 weeks. That's the absolute minimum for a good experience.

Support Lead: That's painful because we could lose the big deal if we wait. But it's better to do it right.

PM: Agreed. Let's scope this for the Q4 roadmap. I'll add it to the strategy doc this week.

Support Lead: One more thing—when you frame the requirements, call out that enterprise accounts need their IT to approve calendar integrations. That's slowing down their adoption pilots.

PM: Good point, I'll capture that. This stays in scope for scheduling, not calendar sync or other integrations.

Engineer Lead: Perfect. Let's prototype one flow next sprint to de-risk the API work.

PM: Sounds good. We're done on this one.
