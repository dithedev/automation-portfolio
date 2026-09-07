# Contributing

Contributions that improve reliability, documentation, test coverage, or compatibility are welcome.

## Before Opening a Pull Request

1. Do not include credentials, webhook URLs, chat IDs, or real invoices.
2. Use synthetic fixtures only.
3. Keep the MVP scope narrow.
4. Update `docs/test-cases.md` for behavior changes.
5. If the extraction contract changes, update both the canonical schema and the schema embedded in `Extract Invoice with OpenAI`.
6. Run `python scripts/generate_demo_invoices.py`.
7. Run `python scripts/validate_artifacts.py`.
8. Import changed workflow JSON into a current n8n instance and record the tested n8n version in the pull request.
9. Before committing an n8n export, remove or replace instance-specific credential IDs, workflow IDs, spreadsheet IDs, webhook URLs, and chat IDs.

## Commit Style

Use short imperative messages, for example:

- `Add duplicate invoice test case`
- `Handle Responses API refusal output`
- `Document Gmail attachment setup`
