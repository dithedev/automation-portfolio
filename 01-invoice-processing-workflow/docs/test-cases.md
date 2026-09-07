# Test Cases

Run every applicable test through the webhook first. Repeat valid and multi-file scenarios through Gmail after configuring the `invoice-intake` label and filter.

| ID | Input | Expected path | Expected Sheets result | Expected notification |
|---|---|---|---|---|
| INV-001 | `invoice-001.pdf` | Valid → new → extraction → processed | One row, `processed` | Invoice processed |
| INV-002 | Send `invoice-001.pdf` again | Valid → duplicate | No additional row | Duplicate skipped |
| INV-003 | `invoice-002.pdf` | Valid → new → extraction → needs review | One row with `missing:invoice_number` | Needs review |
| INV-004 | `invoice-003.pdf` | Valid → new → extraction → needs review | One row with `totals_mismatch` | Needs review |
| INV-005 | `not-an-invoice.txt` | Rejected before AI | No row | Unsupported file extension |
| INV-006 | Request without a `data` file field | Rejected before AI | No row | No binary PDF data found |
| INV-007 | PDF larger than 10 MiB | Rejected before AI | No row | File too large |
| INV-008 | Labeled Gmail message with two PDFs | Rejected before AI | No row | Expected exactly one PDF |
| INV-009 | Controlled Google Sheets failure | Global error workflow | No successful row | Workflow failed alert |
| INV-010 | Temporarily invalid OpenAI credential | Retries, then AI failure path | No row | Processing failure alert |
| INV-011 | `meeting-notes.pdf` or another non-invoice PDF | Extraction → needs review | One row, `not_invoice` | Needs review |
| INV-012 | Text file renamed `fake-invoice.pdf` | Rejected by PDF signature check | No row | Invalid PDF signature |
| INV-013 | Unlabeled Gmail message with a PDF | Gmail trigger ignores message | No row | No notification |

## Detailed Assertions

### INV-001: Valid invoice

- `invoice_number`: `ACME-2026-0042`;
- `vendor_name`: `ACME Automation Labs`;
- `currency`: `EUR`;
- `subtotal`: `1000`;
- `tax_amount`: `210`;
- `total_amount`: `1210`;
- `review_reasons`: empty;
- status: `processed`.

Model confidence is not deterministic, but this clean synthetic document should normally meet the `0.85` threshold. If it does not, record whether extraction quality or the threshold caused review. Do not alter expected invoice data to match an incorrect response.

### INV-003: Missing invoice number

- `invoice_number`: null or empty;
- `review_reasons` contains `missing:invoice_number`;
- status: `needs_review`.

### INV-004: Mismatched totals

```text
700.00 + 147.00 = 847.00
printed total = 900.00
```

The workflow must preserve the printed values and add `totals_mismatch`. It must not silently repair the total.

### INV-005 and INV-012: Content-aware checks

`not-an-invoice.txt` must fail extension/MIME checks. For INV-012, copy it as `fake-invoice.pdf` and upload that copy as PDF. It must still fail because its bytes lack a PDF signature near the beginning. These tests prove the workflow does not trust only filename or MIME metadata.

### INV-008 and INV-013: Gmail routing

- INV-008 must carry `invoice-intake` and contain exactly two PDF attachments.
- INV-013 must have a PDF but no `invoice-intake` label.
- The Gmail query is `label:invoice-intake has:attachment filename:pdf`.

## Error Workflow Test

This test must use an automatic production execution. A manual execution or test webhook does not reliably invoke an Error Trigger workflow.

1. After successful setup, confirm `Invoice Processing & Review - Error Handler` is selected as the main workflow's **Error Workflow**.
2. Connect the Telegram credential in the error workflow and confirm `INVOICE_ALERT_CHAT_ID` is available.
3. Activate both the main workflow and the error workflow.
4. Create a disposable test spreadsheet or temporarily remove access to it.
5. Point `Append Invoice Record` at that controlled target.
6. Submit a PDF with a hash not already in the log through the production webhook URL or the Gmail trigger.
7. Confirm failure at `Append Invoice Record` and confirm no successful row is appended.
8. Confirm Telegram receives a redacted workflow-failure alert with workflow name, execution ID, last node, and timestamp.
9. Restore the correct document and permissions immediately.

Never delete or damage a real business spreadsheet to test failure handling.

## OpenAI Failure-Path Test

This test must use an automatic production execution if the global Telegram failure alert is being asserted.

1. Confirm `Invoice Processing & Review - Error Handler` is selected as the main workflow's **Error Workflow** and both workflows are active.
2. Temporarily select an invalid test credential in `Extract Invoice with OpenAI`.
3. Submit a PDF whose hash is not already present through the production webhook URL or the Gmail trigger.
4. Confirm `Extract Invoice with OpenAI` retries and `AI Processing Error?` routes to `Stop - AI Processing Failed`.
5. Confirm no invoice row is appended.
6. Confirm the global error workflow sends a Telegram workflow-failure alert.
7. Restore the valid credential.

## Test Record Template

| Test ID | Date | n8n version | Result | Execution ID | Notes |
|---|---|---|---|---|---|
| INV-001 | | | Not run | | |
| INV-002 | | | Not run | | |
| INV-003 | | | Not run | | |
| INV-004 | | | Not run | | |
| INV-005 | | | Not run | | |
| INV-006 | | | Not run | | |
| INV-007 | | | Not run | | |
| INV-008 | | | Not run | | |
| INV-009 | | | Not run | | |
| INV-010 | | | Not run | | |
| INV-011 | | | Not run | | |
| INV-012 | | | Not run | | |
| INV-013 | | | Not run | | |
