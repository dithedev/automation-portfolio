# Acceptance Test Cases

Use only synthetic contacts when running these acceptance tests.

| ID | Fixture / condition | Expected result | External effects |
|---|---|---|---|
| LEAD-001 | `lead-001.json` | HTTP 202, `hot`, score ≥75 | HubSpot upsert, Telegram hot alert, Gmail draft, audit row |
| LEAD-002 | Repeat LEAD-001 with same key | HTTP 200, `duplicate` | No AI call, no new CRM action, draft, alert, or audit row |
| LEAD-003 | `lead-002.json` | HTTP 202, `warm` | HubSpot upsert, Gmail draft, audit row; no urgent alert |
| LEAD-004 | `lead-003.json` | HTTP 202, score 22; `cold` when extraction confidence is ≥0.65, otherwise `needs_review` only for `low_confidence` | HubSpot upsert and audit row; review alert only on the safe fallback path |
| LEAD-005 | `lead-004.json` | HTTP 202, `needs_review` | HubSpot upsert, review alert, audit row; no Gmail draft |
| LEAD-006 | `lead-005.json` | HTTP 400 `INVALID_INPUT` | No AI, CRM, Gmail, Telegram, or audit call |
| LEAD-007 | `lead-006.json` | HTTP 422 `CONSENT_REQUIRED` | No persistence or downstream call |
| LEAD-008 | Temporarily select an invalid OpenAI credential or unavailable model | Retries, then `needs_review` | HubSpot upsert, review alert, audit row |
| LEAD-009 | Temporarily set the HubSpot Email field to the failing expression documented below | HTTP 503 `CRM_UPSERT_FAILED` | Failure audit row and technical alert |
| LEAD-010 | Reuse the LEAD-001 email with changed company/phone and a new idempotency key | HTTP 202, normal reprocessing | Same HubSpot record updated; no duplicate contact |
| LEAD-011 | Send a message longer than 4,000 characters through stdin with `--data-binary "@-"` | HTTP 400 `INVALID_INPUT` | No oversized text sent to AI |
| LEAD-012 | Temporarily set `LEAD_AUDIT_SHEET_ID` to an invalid value, then call the active production webhook | Execution fails after retries | Error Workflow sends technical alert; no false success response |
| LEAD-013 | `lead-007.json` | Instruction is treated as enquiry data; never forced to score 100 | No unauthorized action; expected cold/review routing |

## PowerShell example

```powershell
$headers = @{
  "X-Lead-Token" = "REPLACE_WITH_SECRET"
  "Idempotency-Key" = "demo-lead-001"
}

Invoke-RestMethod `
  -Method Post `
  -Uri "https://YOUR_N8N_HOST/webhook-test/lead-intake" `
  -Headers $headers `
  -ContentType "application/json" `
  -InFile ".\demo\requests\lead-001.json"
```

## LEAD-004 — model confidence boundary

The deterministic score for `lead-003.json` is 22. The expected business tier is `cold`, but the safety gate has precedence over the score: if the extractor returns confidence below 0.65, the workflow must route the lead to `needs_review` with `low_confidence`.

This means both of these outcomes are valid:

- `cold` with score 22 and confidence ≥0.65;
- `needs_review` with score 22 and `low_confidence`.

The fixture must never become `warm` or `hot`. Record the model and confidence in the test evidence instead of weakening the safety threshold to force a deterministic label.

## LEAD-008 — simulate an OpenAI failure

1. Open `OpenAI Chat Model`.
2. Temporarily select an invalid test credential or enter a model name that is unavailable to the account.
3. Submit a valid fixture with a new idempotency key.
4. Confirm that the model call retries and the workflow then continues through the safe `needs_review` fallback.
5. Confirm the HubSpot upsert, review alert, and audit row.
6. Restore the working credential and model immediately after the test.

## LEAD-009 — simulate a HubSpot failure

Do not disconnect, delete, or replace the HubSpot credential. Instead:

1. Open `HubSpot Create or Update Contact`.
2. Temporarily replace the Email expression with:

   ```javascript
   ={{ (() => { throw new Error('Simulated HubSpot failure') })() }}
   ```

3. Start a test execution and submit a valid fixture with a new idempotency key.
4. Confirm the `CRM_UPSERT_FAILED` response, failure audit row, and technical Telegram alert.
5. Restore the Email expression to:

   ```javascript
   ={{ $json.email }}
   ```

## LEAD-010 — verify HubSpot update instead of duplicate creation

1. In HubSpot, open the contact created by LEAD-001.
2. Record its **Record ID**, create date, and the current number of contacts with that email.
3. In PowerShell, load `lead-001.json`, change only company and phone in memory, and send it with a new idempotency key:

   ```powershell
   $body = Get-Content ".\demo\requests\lead-001.json" -Raw | ConvertFrom-Json
   $body.company = "Brightpath Logistics Updated"
   $body.phone = "+1 202 555 0199"

   $headers = @{
     "X-Lead-Token" = "REPLACE_WITH_SECRET"
     "Idempotency-Key" = "demo-lead-010-$([DateTimeOffset]::UtcNow.ToUnixTimeSeconds())"
   }

   $jsonBody = $body | ConvertTo-Json -Depth 10 -Compress

   Invoke-RestMethod `
     -Method Post `
     -Uri "https://YOUR_N8N_HOST/webhook-test/lead-intake" `
     -Headers $headers `
     -ContentType "application/json" `
     -Body $jsonBody
   ```

4. Refresh the contact in HubSpot and verify all of the following:
   - the Record ID is unchanged;
   - the create date is unchanged;
   - only one contact exists with that email;
   - Company Name is `Brightpath Logistics Updated`;
   - Phone Number is `+1 202 555 0199`.

## LEAD-011 — message longer than 4,000 characters

Build the JSON in PowerShell and pipe it to `curl.exe`. The `--data-binary "@-"` argument makes curl read the request body from stdin without creating a temporary fixture:

```powershell
$headers = @(
  "X-Lead-Token: REPLACE_WITH_SECRET",
  "Idempotency-Key: demo-lead-011"
)

$body = @{
  name = "Long Message Test"
  email = "long-message@example.com"
  company = "Northstar Test"
  phone = "+37060000000"
  message = "A" * 4001
  estimated_budget = 1000
  currency = "EUR"
  consent_to_contact = $true
} | ConvertTo-Json -Compress

$body | curl.exe -i -X POST `
  "https://YOUR_N8N_HOST/webhook-test/lead-intake" `
  -H $headers[0] `
  -H $headers[1] `
  -H "Content-Type: application/json" `
  --data-binary "@-"
```

## LEAD-012 — simulate an audit-sheet failure

This test must use an automatic production execution because n8n Error Workflows do not run for manual test executions.

1. Make sure both workflows are active and the Error Workflow is selected in the main workflow settings.
2. In n8n, open **Settings → Variables** and temporarily replace the value of `LEAD_AUDIT_SHEET_ID` with:

   ```text
   invalid-spreadsheet-id-for-lead-012
   ```

   Do not edit `Append Lead Audit`: changing its Document field can reset the dependent Sheet and mapping parameters.

3. Submit a valid fixture with a new idempotency key to the production URL:

   ```text
   https://YOUR_N8N_HOST/webhook/lead-intake
   ```

4. Confirm that `Append Lead Audit` exhausts its retries and the Error Workflow sends the technical alert.
5. Restore the real value of `LEAD_AUDIT_SHEET_ID` immediately after the test.
6. Run one normal request and confirm that audit writes work again.

## Acceptance evidence

A complete acceptance run verifies:

- validation stops rejected input before AI;
- extraction conforms to the configured schema;
- scoring output includes `score_breakdown`;
- HubSpot receives Company Name and Phone Number;
- LEAD-010 keeps the original HubSpot Record ID and create date, creates no duplicate, and updates company and phone;
- hot and `needs_review` notifications reach their intended paths;
- successful and failed audit rows are written correctly;
- an unhandled production execution failure invokes the Error Workflow.
