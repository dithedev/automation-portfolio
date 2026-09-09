# Operations Runbook

## Status meanings

- `completed`: CRM upsert and audit append succeeded.
- `duplicate`: an audit row already exists for the idempotency key; no side effects repeated.
- `needs_review`: accepted, but AI output was unavailable, uncertain, or incomplete.
- `failed`: the CRM operation failed and the lead was preserved in the failure audit.
- `rejected`: input or consent requirements were not met.

## Retry policy

OpenAI, HubSpot, and Google Sheets operations attempt up to three executions with a short delay. This protects against brief transient failures without creating unbounded retry storms. Increase delays only after observing provider rate limits and add exponential backoff if the deployment receives sustained traffic.

## Manual recovery: CRM failure

1. Find the audit row with `status=failed` and `error_code=CRM_UPSERT_FAILED`.
2. Open the corresponding n8n execution using `request_id`/execution ID.
3. Confirm the original input remains authorized for processing.
4. Correct the credential or provider problem.
5. Retry from the HubSpot node only if doing so will not repeat earlier side effects.
6. Confirm the contact exists and update the audit status manually or through a future recovery workflow.

The long-lived audit intentionally omits the full message and email. Recovery therefore uses n8n execution data, whose retention must be configured for the deployment.

## Manual review

Reviewers should verify service, timeline, budget, and authority from the original enquiry. They may edit and send a Gmail draft, but the workflow never performs that final action.

## Monitoring

At minimum monitor:

- executions ending in error;
- CRM failure alerts;
- volume of `needs_review`;
- duplicate ratio;
- OpenAI latency and cost;
- age of unresolved failed audit rows.

## Retention

Define separate retention periods for n8n execution data, HubSpot contacts, Gmail drafts, Telegram notifications, and the audit sheet. Delete test records after validation. Production retention must follow the organization's legal basis and privacy policy.

## Safe changes

Any change to scoring weights or thresholds increments `scoring_version` and updates `docs/scoring.md` and `CHANGELOG.md`. Test all four tiers before activation.
