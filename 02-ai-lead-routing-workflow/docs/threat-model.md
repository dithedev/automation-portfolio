# Threat Model

## Assets

- Lead contact data and enquiry content.
- n8n, OpenAI, HubSpot, Google, and Telegram credentials.
- CRM integrity and audit accuracy.
- Paid API quota.

## Trust boundaries

1. Public caller → authenticated webhook.
2. Untrusted enquiry text → AI provider.
3. n8n → HubSpot, Google, OpenAI, and Telegram.
4. n8n execution storage → operators.

## Risks and controls

| Risk | Control | Residual risk |
|---|---|---|
| Unauthorized webhook use | Header Auth credential | Secret theft or sharing; rotate and monitor |
| Replay / duplicate side effects | Required idempotency key checked before AI | Google Sheets has weak concurrency guarantees |
| Prompt injection in message | Explicit data boundary; no tools exposed to model | Model may still misclassify; deterministic review gate limits impact |
| Invalid structured output | Manual JSON Schema and confidence gate | Correct shape does not guarantee correct meaning |
| Contact duplication | Native HubSpot create/update by normalized email | Aliases and changed addresses may represent the same person |
| Data leakage in audit | Masked email; message excluded; bounded errors | External systems still receive data required for their action |
| Accidental automated outreach | Gmail draft only | A human can still send an incorrect draft |
| Provider outage | Bounded retry, CRM failure audit, alerts | No durable queue in MVP |
| Secret leakage in repository | Credentials omitted; CI secret-pattern scan | New workflow exports still require review |
| Excessive AI cost | Validation and idempotency precede AI; 4,000-char limit | No per-client rate limiter in n8n workflow |

## Data sent to providers

- OpenAI: name, company, explicit budget, source, and enquiry text.
- HubSpot: email, first/last name, company, phone, lifecycle stage.
- Google Sheets: masked email and operational metadata; not the original message.
- Gmail: recipient email and deterministic draft content.
- Telegram: name, company, summary, score/review reasons, and request ID; never full email or phone.

## Production hardening

Use a transactional database with a unique idempotency constraint, enforce rate limiting upstream, restrict CORS, apply data-retention policies, use least-privilege credentials, add alert delivery redundancy, and test concurrent requests before a real deployment.
