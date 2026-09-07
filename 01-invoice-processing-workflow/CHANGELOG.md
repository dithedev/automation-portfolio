# Changelog

All notable changes to this project will be documented in this file.

## [0.1.1] - 2026-09-07

### Changed

- replaced the temporary OpenAI Files API upload/delete sequence with direct PDF input through n8n's native OpenAI node;
- restricted Gmail intake to the `invoice-intake` label, PDF attachments, and PDF filenames;
- renamed synthetic fixtures to neutral `invoice-001.pdf`, `invoice-002.pdf`, and `invoice-003.pdf` names;
- removed semantic PDF title and author metadata;
- updated setup, test cases, threat model, CI, and environment documentation.

### Security

- strengthened `Validate and Hash` to check actual bytes, size, extension, allowed MIME values, and the `%PDF-` signature before AI processing;
- added tests for a text file disguised as `fake-invoice.pdf` and for unlabeled Gmail messages;
- documented export sanitization and the security limits of Gmail labels and PDF signature checks.

### Fixed

- aligned duplicate handling, AI failure routing, Google Sheets mapping, and Telegram error reporting with the importable workflows;
- updated artifact validation for the neutral fixture names and absence of hidden model hints.

## [0.1.0] - 2026-08-20

### Added

- webhook and Gmail PDF intake;
- PDF validation and SHA-256 duplicate detection;
- OpenAI Responses API extraction with strict JSON Schema;
- deterministic invoice validation;
- processed and human-review routing;
- Google Sheets audit storage;
- Telegram notifications;
- companion error workflow;
- synthetic invoice fixtures and documented test cases.
