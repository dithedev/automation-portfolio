# Deterministic lead scoring

The LLM extracts signals; it never decides the lead tier. The `Calculate Explainable Score` node applies the following versioned rules.

## Score components

| Component | Signal | Points |
|---|---|---:|
| Budget | 20k+ | 30 |
| Budget | 10k–20k | 24 |
| Budget | 5k–10k | 16 |
| Budget | Under 5k | 6 |
| Budget | Unknown | 0 |
| Urgency | Immediate | 25 |
| Urgency | Within one month | 20 |
| Urgency | This quarter | 10 |
| Urgency | Exploring | 2 |
| Decision maker | Strong | 20 |
| Decision maker | Medium | 10 |
| Decision maker | Weak | 3 |
| Service fit | Core service | 15 |
| Company supplied | Yes | 5 |
| Useful message | At least 80 characters | 5 |

Maximum: 100 points.

## Tier rules

1. `needs_review` overrides the numeric tier when AI confidence is below `0.65`, service is unclear, urgency is unclear, the AI call fails, or the structured result is missing.
2. Otherwise `hot` is 75–100.
3. Otherwise `warm` is 45–74.
4. Otherwise `cold` is 0–44.

The workflow emits both the total and a `score_breakdown` object. Changing thresholds or weights requires a changelog entry because it changes business behavior.

## Guardrails

- Protected or sensitive personal characteristics are never inputs to scoring.
- Email provider, name, geography, and writing style do not affect the score.
- A low score means low fit for this fictional service workflow, not low human value.
- The system does not automatically send outreach or reject a person.
