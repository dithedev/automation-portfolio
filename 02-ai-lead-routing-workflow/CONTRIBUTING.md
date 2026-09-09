# Contributing

1. Open an issue describing the business or reliability problem.
2. Never include real leads, credentials, workflow URLs, account IDs, or execution exports.
3. Update tests and documentation for behavior changes.
4. Run `python scripts/generate_demo_requests.py --check`, `python scripts/validate_artifacts.py`, and `node scripts/test_scoring.mjs` before submitting a pull request.

Changes to scoring require a new `scoring_version`, updated scoring documentation, and acceptance tests for all four routing tiers.
