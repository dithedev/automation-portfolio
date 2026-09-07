# Setup Guide

## 1. Before You Start

Use a current n8n Cloud workspace or a current self-hosted n8n release. The workflows use Webhook 2.x, Gmail Trigger 1.x, Code 2.x, Google Sheets 4.x, Telegram 1.x, and the native OpenAI node 2.x.

Keep both workflows inactive until configuration and testing are complete.

n8n exports do not contain credential secrets, but they can contain instance-specific credential names and IDs, spreadsheet IDs, and workflow IDs. After importing, reselect your own credentials and resources. Before publishing a new export, remove or replace instance-specific metadata.

## 2. Create the Google Sheet

1. Create a Google spreadsheet.
2. Create or rename a tab to exactly `Invoices`.
3. Import `demo/google-sheets-template.csv` into that tab.
4. Delete the example data row but keep the header row unchanged.
5. In `Find Existing Hash`, select your Google credential, document, and `Invoices` tab.
6. Repeat the selection in `Append Invoice Record` and refresh its column mapping.

Required columns:

```text
processed_at
request_id
file_hash
file_name
source
status
review_reasons
document_type
invoice_number
vendor_name
invoice_date
due_date
currency
subtotal
tax_amount
total_amount
confidence
model
```

Do not rely on a spreadsheet ID carried over from the imported JSON. Selecting the document and tab in n8n also loads the current column schema.

## 3. Route Only Invoice Emails to n8n

The Gmail Trigger is restricted to:

```text
label:invoice-intake has:attachment filename:pdf
```

Before activating the workflow:

1. In Gmail, open **Settings → See all settings → Labels**.
2. Create a label named exactly `invoice-intake`.
3. Open **Settings → Filters and Blocked Addresses → Create a new filter**.
4. For this demo, set **Subject includes** to `[INVOICE]` and enable **Has attachment**.
5. Select **Apply the label → invoice-intake** and save the filter.
6. In `Gmail Invoice Trigger`, confirm **Download Attachments** is enabled and the search query matches the value above.

For tests, put `[INVOICE]` in the subject. The label is routing, not authentication. In production, use a dedicated mailbox or an approved-sender rule.

## 4. Configure Credentials

| Credential | Nodes | Notes |
|---|---|---|
| Header Auth | `Webhook Invoice Upload` | Suggested header: `X-Invoice-Token`; use a long random secret |
| Gmail OAuth2 | `Gmail Invoice Trigger` | Gmail read permission and attachment download |
| OpenAI API | `Extract Invoice with OpenAI` | Use a project-scoped key with a suitable budget |
| Google Sheets OAuth2 | `Find Existing Hash`, `Append Invoice Record` | Read and write access to the selected sheet |
| Telegram API | Three main notification nodes and error workflow's `Send Error Alert` | Use a dedicated test bot and private chat |

Never paste a key into an expression, Code node, workflow name, or committed JSON.

## 5. Create the n8n Variable

Create:

```text
INVOICE_ALERT_CHAT_ID=<your-private-test-chat-id>
```

Telegram nodes read `$vars.INVOICE_ALERT_CHAT_ID`. If your plan lacks variables, use a fixed test chat ID in your private instance and do not publish that edited export.

## 6. Import and Connect the Workflows

1. Import `workflows/invoice-processing-error.json`.
2. Connect its Telegram credential and save it.
3. Import `workflows/invoice-processing-main.json`.
4. Connect all credentials listed above.
5. Reselect the spreadsheet and `Invoices` tab in both Sheets nodes.
6. In the main workflow settings, set **Error Workflow** to `Invoice Processing & Review - Error Handler`.
7. Save the main workflow without activating it.

An Error Trigger workflow is invoked by a failed automatic execution. Manually executing the Error Trigger is not a valid end-to-end test.

## 7. Test the Webhook Path

1. Keep the main workflow inactive.
2. Open `Webhook Invoice Upload` and listen for a test event.
3. Send a multipart request with the PDF in a field named exactly `data`.
4. Include the configured authentication header.
5. Confirm the execution reaches Sheets and Telegram and appends exactly one row.
6. Send the same PDF again and confirm no second row is created.

```bash
curl -X POST "<TEST_WEBHOOK_URL>" \
  -H "X-Invoice-Token: <YOUR_SECRET>" \
  -F "data=@demo/invoices/invoice-001.pdf;type=application/pdf"
```

The webhook contract is strict: a different binary field name is rejected as a missing file.

## 8. Test the Gmail Path

1. Confirm the `invoice-intake` label and filter exist.
2. Send a message with `[INVOICE]` in the subject and exactly one PDF.
3. Confirm Gmail applies the label, then wait for the one-minute trigger poll.
4. Confirm processing, the Sheets row, and Telegram notification.
5. Send a labeled message with two PDFs and confirm rejection before OpenAI.
6. Send an unrelated, unlabeled PDF message and confirm it does not start the workflow.

## 9. File Validation and Model Configuration

`Validate and Hash` does not trust only client metadata. Before any paid model call it verifies:

- binary property `data` exists;
- file is non-empty and no larger than 10 MiB;
- filename ends in `.pdf`;
- MIME type is PDF-compatible or absent;
- `%PDF-` occurs within the first 1024 bytes;
- SHA-256 can be calculated from the actual bytes.

This is an intake check, not malware scanning or complete PDF validation.

`Extract Invoice with OpenAI` uses the native n8n OpenAI node and sends the PDF binary directly to the Responses API. It uses `gpt-4o-mini`, a JSON Schema response format, and `store: false`. There is no separate Files API upload or delete step.

`Validate Invoice Data` then checks required fields, document type, confidence, date and currency formats, non-negative amounts, and `subtotal + tax_amount = total_amount` with tolerance `0.02`. A schema-valid response can still become `needs_review`.

## 10. Activate

Activate only after the Gmail routing works, all credentials and Sheets mappings are correct, Telegram messages arrive, the error workflow is selected, every test passes, and the example row is removed.

## 11. Troubleshooting

### No binary attachment

- Webhook: send multipart form data with the field named `data`.
- Gmail: enable **Download Attachments** and verify the message has the label and PDF.

### Gmail does not start the workflow

- Confirm the workflow is active for production polling.
- Confirm the exact query is `label:invoice-intake has:attachment filename:pdf`.
- Verify Gmail actually applied the label and allow for the one-minute poll.

### A real PDF is rejected

- Check its filename extension and MIME type in the execution data.
- Confirm `%PDF-` appears near the start of the file.
- An unusual valid PDF may need a documented change to the 1024-byte window; do not remove the content check entirely.

### Google Sheets produces no result

- Verify the tab is exactly `Invoices` and the header row exists.
- Reselect the document and tab after connecting credentials.
- Refresh and remap columns in `Append Invoice Record` if needed.

### OpenAI extraction fails

- Confirm credential, project budget, and model support for PDF input and structured JSON.
- Inspect `Extract Invoice with OpenAI` and the `AI Processing Error?` branch.
- Do not bypass `Validate Invoice Data` to make a test pass.

### Error workflow does not run

- Confirm it is selected in main workflow settings.
- Test with an automatic execution; manual runs can behave differently.
- Confirm `Send Error Alert` has a Telegram credential and chat ID.
