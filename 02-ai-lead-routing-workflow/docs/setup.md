# Setup Guide

## 1. Requirements

- n8n Cloud or self-hosted n8n 2.37+
- OpenAI credential
- HubSpot account connected to n8n
- Google account with Sheets and Gmail access
- Telegram bot and a private test chat

Use separate test accounts where practical. Never test with real customer data.

## 2. Create the audit sheet

1. Create a Google spreadsheet.
2. Import `demo/google-sheets-template.csv`.
3. Name the tab exactly `Leads`.
4. Keep the header row unchanged.
5. Copy the spreadsheet ID from its URL.
6. In n8n, open **Settings → Variables** and create:

   ```text
   Key: LEAD_AUDIT_SHEET_ID
   Value: your spreadsheet ID
   ```

Create this variable before importing or configuring the main workflow. Do not paste the spreadsheet ID directly into the Google Sheets nodes: changing the Document parameter makes n8n reset the dependent Sheet and column-mapping parameters.

The sheet intentionally stores a masked email and omits the original message.

## 3. Import the Error Workflow

1. Import `workflows/lead-routing-error.json`.
2. Open `Send Technical Alert` and select a Telegram credential.
3. Create the n8n variable `LEAD_ALERT_CHAT_ID` containing the test chat ID. Enter the variable name exactly as shown, without backslashes.
4. Save and activate the Error Workflow.

If your n8n plan does not support Variables, replace `$vars.LEAD_ALERT_CHAT_ID` in every Telegram node with a fixed chat ID. Remove account-specific values from any workflow export shared outside that n8n instance.

## 4. Import the Main Workflow

Import `workflows/lead-routing-main.json`, but do not activate it yet.

### Header Auth

Create an n8n Header Auth credential:

```text
Name: X-Lead-Token
Value: a long random secret
```

Select it in `Protected Lead Webhook`. The secret is not exported in the workflow JSON.

### OpenAI

Select your credential in `OpenAI Chat Model`. Keep `Use Responses API` enabled. The default model is `gpt-4o-mini`; verify that it is available in your account before testing.

Extraction confidence is model-dependent. In the cold-lead fixture, `gpt-4o-mini` may return confidence below 0.65 and therefore trigger the intentional `needs_review` safety fallback, while `gpt-4o` may return `cold`. Do not lower the confidence threshold merely to force the fixture into a particular tier; record the model and confidence with the acceptance result.

### HubSpot

Connect HubSpot through the credential method shown by your current n8n version. Grant only the contact scopes required to read/write CRM contacts. Select the credential in `HubSpot Create or Update Contact`.

The imported node is preconfigured with `Contact` → `Create or Update` and an email expression. After selecting the credential, confirm that the Email field still shows `{{ $json.email }}` in Expression mode. You should not need to re-select the operation or rebuild the expression.

The MVP uses standard contact fields only: email, first name, last name, company name, phone number, and lifecycle stage. In the imported n8n node, confirm that the visible **Company Name** and **Phone Number** fields contain the expressions `{{ $json.company }}` and `{{ $json.phone }}`. The underlying n8n parameter names are `companyName` and `phoneNumber`; using `company` or `phone` as node parameter names does not populate the HubSpot properties. No custom HubSpot properties or pipeline IDs are required.

### Google Sheets

Select your Google Sheets credential in all three nodes below:

- `Find Idempotency Key`;
- `Append Lead Audit`;
- `Append Failed Lead Audit`.

The Document field is already set to `{{ $vars.LEAD_AUDIT_SHEET_ID }}` and the Sheet field to `Leads`. Do not replace the Document expression inside the nodes. Confirm that both append nodes show `Map Automatically` and retain all 19 cached columns.

If Variables are unavailable on your n8n plan, configure each Google Sheets node manually in this exact order: Document, then Sheet `Leads`, then Mapping Column Mode `Map Automatically`. The n8n editor resets dependent fields whenever Document changes, so the later two settings must be applied after the spreadsheet ID.

### Gmail

Select a Gmail credential in:

- `Create Hot Follow-up Draft`;
- `Create Warm Follow-up Draft`.

These nodes create drafts addressed to the synthetic test email. They do not send messages.

### Telegram

Select the same Telegram credential in:

- `Alert Sales - Hot`;
- `Alert Human Review`;
- `Alert Technical Failure`.

Keep Parse Mode set to `HTML` in these nodes. Their dynamic values are HTML-escaped inside the message expressions, so names, summaries, and error text containing `<`, `>`, or `&` cannot break delivery. If you edit a message later, preserve the escaping helper used in its expression.

## 5. Link the Error Workflow

Open the main workflow settings and choose `AI Lead Intake & CRM Routing - Error Handler` as its Error Workflow.

Keep successful automatic execution data disabled unless you have a defined retention requirement. The audit sheet contains the intended long-lived operational record.

## 6. Test safely

1. Open `Protected Lead Webhook`.
2. Start listening on the test URL.
3. Send one fixture from `demo/requests`.
4. Inspect every node output before proceeding.
5. Follow `docs/test-cases.md` in order.
6. Delete synthetic contacts and Gmail drafts after testing if desired.

The test webhook normally requires one listening execution per request. Use the production URL only after activation.

## 7. Activate

Before activation, verify:

- no node is red;
- all credentials are selected;
- the spreadsheet placeholder no longer appears;
- Telegram uses the intended private chat;
- Error Workflow is linked;
- all acceptance tests pass;
- workflow JSON exported for GitHub contains no credential IDs or account data.

Restrict `allowedOrigins` in the webhook node if the workflow is called from a known web application. Header authentication remains mandatory.

## 8. Validate workflow exports

After changing either workflow, export it from n8n and verify that credential references, pinned execution data, account-specific IDs, and generated webhook IDs are absent. Then run:

```bash
python scripts/validate_artifacts.py
```

The repository must contain workflow definitions, not execution payloads. This project's CI definition is stored at the monorepo root in `.github/workflows/02-validate-lead-routing.yml`.
