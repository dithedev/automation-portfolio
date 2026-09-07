# Lightweight Threat Model

## Assets

- invoice PDF content and extracted financial data;
- Gmail, OpenAI, Google, and Telegram credentials;
- webhook authentication secret;
- Google Sheets processing history;
- n8n execution data and instance metadata.

## Trust Boundaries

1. Email sender or webhook client to n8n.
2. Gmail to the n8n Gmail Trigger.
3. n8n to OpenAI, Google Sheets, and Telegram.
4. n8n editors and execution viewers.

## Key Risks and Controls

| Risk | MVP control | Residual risk |
|---|---|---|
| Unauthorized webhook upload | Header authentication | Secret leakage, replay, and high request volume remain possible |
| Unrelated or malicious email intake | Gmail query requires `invoice-intake`, attachment, and PDF filename | A label is routing, not sender authentication; a bad filter or compromised mailbox can admit files |
| Spoofed file metadata | Actual bytes, size, extension, allowed MIME, and `%PDF-` signature are checked | Signature checking is not malware scanning or complete PDF parsing |
| Oversized file or cost abuse | 10 MiB limit before OpenAI | Many allowed-size requests can still consume budget |
| Duplicate model spend | SHA-256 lookup before OpenAI | Byte-different copies are not detected; Sheets does not enforce atomic uniqueness |
| Prompt injection in document | Invoice is treated as data and model has no tools | Injected text can still influence extracted fields |
| Incorrect model values | JSON Schema plus deterministic field, format, confidence, and total checks | Schema and arithmetic do not prove factual correctness |
| Sensitive vendor processing | Direct PDF input and `store: false`; no Files API upload | Data is still sent to the provider under its current account and retention policies |
| Credential exposure | n8n credential store; no API secrets in project files | Administrators are privileged; exports can expose non-secret credential names and IDs |
| Sensitive execution logs | No original PDF in notifications; error formatter redacts API-key-like strings | Executions may contain filenames, extracted fields, and service errors |
| Spreadsheet tampering | Restricted Google access | Sheets is not immutable and lookup can race under concurrent executions |
| Notification leakage | Private Telegram test chat | Telegram still receives invoice status and summary data |
| Provider outage | Retries and explicit AI failure branch | Prolonged outages require replay or manual handling |

## Security Assumptions

- Gmail label/filter is reviewed before activation.
- Webhook is served over HTTPS.
- Credentials exist only in n8n, not expressions or Code nodes.
- Telegram destination is a private test chat.
- Sheets contains demo or appropriately authorized data.
- n8n execution viewers are trusted to see processed business data.

## Production Hardening Beyond MVP

- rate-limit the webhook and rotate its secret;
- add replay protection or signed requests;
- use a dedicated mailbox and approved-sender allowlist;
- quarantine and malware-scan attachments;
- validate PDFs with a hardened isolated parser;
- replace Sheets deduplication with a database unique constraint on `file_hash`;
- define encryption, deletion, and retention policies;
- prune n8n execution data and restrict viewer access;
- redact filenames and business data from alerts;
- publish sanitized exports without instance-specific credential, workflow, or spreadsheet IDs;
- add role-based financial review and a replay queue;
- complete legal, privacy, and vendor-risk review before using real documents.
