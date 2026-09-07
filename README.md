# Automation & AI Portfolio

> Seven demo business cases showcasing practical automation development with n8n, Python, APIs, databases, and LLMs.

![Portfolio](https://img.shields.io/badge/portfolio-Automation%20%26%20AI-2563EB?style=flat-square)
![Projects](https://img.shields.io/badge/projects-1%20%2F%207-F59E0B?style=flat-square)
![Status](https://img.shields.io/badge/status-in%20development-8B5CF6?style=flat-square)
![License](https://img.shields.io/badge/license-MIT-22C55E?style=flat-square)

## About This Portfolio

This repository is the central index for an Automation / AI Automation Specialist portfolio. It brings together seven independent projects and provides quick access to each business case, its architecture, source code, documentation, and demo.

The projects demonstrate the complete journey from analyzing a manual process to delivering a reproducible technical solution: receiving and validating data, integrating multiple systems, implementing deterministic business rules, applying AI where it adds value, handling failures, testing the result, and preparing the project for handoff.

These are demo implementations created for portfolio review and technical exploration. They are not ready-to-deploy production systems and require security review, configuration, and adaptation to the infrastructure and requirements of a specific organization.

## What This Collection Demonstrates

- business process analysis and automation design;
- n8n workflow development;
- Python backend development and API integration;
- webhooks, REST APIs, JSON, and binary file processing;
- integrations with PostgreSQL, Google Sheets, Gmail, Telegram, and CRM-like systems;
- Structured Outputs, RAG, and controlled use of LLMs;
- data validation, deduplication, and idempotency;
- retries, error paths, human review, and audit trails;
- testing, CI, and reproducible setup;
- secure open-source publishing without credentials or user data.

## Projects

Each project is maintained in a separate repository with its own `README.md`, documentation, setup instructions, test data, and demo materials.

| # | Project | Type | Summary | Status |
|---:|---|---|---|---|
| 01 | [Invoice Processing & Review Workflow](https://github.com/dithedev/invoice-processing-workflow) | n8n + AI | Receives PDF invoices, extracts structured data with AI, validates results, prevents duplicates, and routes uncertain documents for human review. | Preparing for release |
| 02 | `ai-lead-routing-workflow` | n8n + AI | Receives leads through a webhook, classifies and scores them, creates CRM records, and routes follow-up actions. | Coming soon |
| 03 | `customer-support-order-routing` | n8n + mock API + AI | Classifies support requests, retrieves order data through an API, and chooses between an automated response and human escalation. | Coming soon |
| 04 | `news-intelligence-pipeline` | Python | Collects RSS sources, removes duplicates, stores articles in PostgreSQL, and delivers topic-based Telegram digests. | Coming soon |
| 05 | `knowledge-base-rag-api` | Python + AI | Ingests a knowledge base, creates embeddings, retrieves relevant context, returns cited answers, and evaluates retrieval quality. | Coming soon |
| 06 | `content-processing-api` | Python + AI + web UI | Extracts content from URLs, produces structured AI output, exposes an API and web interface, and persists processing results. | Coming soon |
| 07 | `customer-data-sync` | n8n, no AI | Synchronizes customer data, reconciles records, handles conflicts, and prevents duplicate operations through idempotent processing. | Coming soon |

Project names marked `Coming soon` will become active links when their repositories are published.

## Portfolio Tracks

| Track | Projects | Skills Demonstrated |
|---|---|---|
| n8n automation | 01, 02, 07 | Workflow design, integrations, branching, reliability, and idempotency |
| Python systems | 04, 05, 06 | Backend development, APIs, databases, testing, and containerization |
| Hybrid architecture | 03 | Connecting low-code workflows with a custom API and AI components |

## How to Explore the Portfolio

1. Choose a project from the table above.
2. Open its dedicated repository.
3. Start with the project `README.md` and architecture diagram.
4. Review the demo, example input and output, and test cases.
5. Follow the setup guide if you want to run it with your own credentials.

> [!IMPORTANT]
> Do not use these demo projects in a production environment without an independent security review, appropriate access controls, and adaptation to your specific business requirements.

## Target Roles

This collection is designed to support applications for roles such as:

- Automation Specialist;
- n8n Automation Developer;
- AI Automation Specialist;
- Workflow Automation Engineer;
- Junior AI Integration / Backend Developer.

## Status

The portfolio is being developed incrementally. A project is added to this page after its implementation, documentation, tests, and demo materials have been completed and reviewed.

## License

The contents of this central repository are available under the [MIT License](./LICENSE). Each project also includes its own licensing information.
