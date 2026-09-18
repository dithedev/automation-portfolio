# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] - 2026-09-18

### Added

- Domain model, PostgreSQL schema (Alembic), repositories, and settings validation
- Trusted feed configuration loading and database seed
- Feed URL / DNS public-IP policy checks and article-link host allowlisting
- Versioned digest prompts with opaque candidate ids
- Unit and integration test foundations (Postgres testcontainers)
- Docker Compose services for Postgres, migrations, API, scheduler, and DB check
- Safe feed HTTP client with conditional requests, size limits, and no redirects
- Feed parsing, URL canonicalization, HTML sanitization (`nh3`), and content hashing
- `FeedIngestionService` with per-source persistence and partial failure handling
- Demo-mode local RSS fixtures and mock LLM / Telegram clients
- Topic profile loading and per-source ingest limit resolution
- Deterministic candidate selection with scoring and source diversity caps
- PostgreSQL advisory lock and full `DigestPipelineService` orchestration
- OpenAI Responses Structured Outputs client with repair pass and error mapping
- Digest post-validation (grounding, length, markup/URL bans, Telegram split)
- Telegram HTML digest rendering (escaped fields, disabled link previews)
- Digest delivery with per-part attempts and retry-delivery CLI
- FastAPI ops API: public health endpoints; `/status` gated by `ADMIN_API_KEY`
- APScheduler process for scheduled digest runs
- SECURITY.md

### Changed

- Feed config path aligned to `config/feeds.yaml`
- Digest item summary validation tightened to 80–280 characters
- Coverage gate includes core application modules (pipeline, ingestion, delivery, clients)
