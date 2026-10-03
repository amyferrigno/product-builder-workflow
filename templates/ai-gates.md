# The 5-Gate AI Decision Framework

When proposing AI for a problem, evaluate all five gates. Each must be pass, fail, or unknown.

## Gate 1: Is it genuinely probabilistic?

Does this problem require dealing with uncertainty or variation, or could finite rules solve it completely?

## Gate 2: Does it match one of the 6 AI patterns?

- **Recognition at scale**: Classify images, text, or entities at high volume (spam detection, content moderation)
- **Personalization beyond rules**: Recommend, rank, or customize based on user/context data that's too fluid for hardcoded rules
- **NLU/NLG**: Understand natural language input or generate natural language output
- **Prediction under uncertainty**: Forecast demand, churn, LTV, or other outcomes
- **Creative augmentation**: Generate new designs, copy, music, or ideas to assist humans
- **Judgment workflow automation**: Make yes/no decisions in a workflow (approve/reject, route, prioritize)

If none fit, the answer is "none", not a reason to default to pass.

## Gate 3: Is the data ready?

Do you have sufficient quantity (training examples, historical data, logs), quality (clean, representative, not stale), and access (can you fetch it in production without latency)?

## Gate 4: What is error tolerance and what happens when wrong?

Define the cost of a false positive and false negative. Can the system degrade gracefully (e.g., show multiple options, flag for human review)?

## Gate 5: Is ROI positive after the hidden-cost iceberg?

Factor in: data cleaning, labelling, continuous evaluation, monitoring, retraining when data drifts, and rebuilding when business logic changes. Avoid: systems that must be retrained weekly, require expensive human annotation, or collapse if data distribution shifts.

## Red flags that override all gates

- **Known finite rules**: A clear decision tree or formula can solve it
- **Insufficient data**: Fewer than ~100 good examples per class, or data can't be collected
- **Catastrophic errors**: Single errors cause material harm (safety, legal, financial)
- **Explainability required**: Regulator or user demands line-by-line justification
- **UX problem in disguise**: The real issue is interaction design, not prediction
- **Commodity tool rebuild**: Replicating a mature tool (ChatGPT, Figma) with a budget constraint
