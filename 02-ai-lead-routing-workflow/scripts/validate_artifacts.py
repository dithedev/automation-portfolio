#!/usr/bin/env python3
"""Offline structural checks for repository artifacts."""

from __future__ import annotations

import csv
import json
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / "workflows"
FIXTURES = ROOT / "demo" / "requests"

EXPECTED_HEADERS = [
    "received_at",
    "request_id",
    "idempotency_key",
    "email_masked",
    "company",
    "source",
    "intent",
    "requested_service",
    "urgency",
    "budget_category",
    "score",
    "tier",
    "score_breakdown",
    "crm_status",
    "hubspot_contact_id",
    "action",
    "status",
    "error_code",
    "error_message",
]

SECRET_PATTERNS = {
    "OpenAI key": re.compile(r"sk-[A-Za-z0-9_-]{20,}"),
    "Bearer token": re.compile(r"Bearer\s+[A-Za-z0-9._-]{20,}", re.I),
    "Google private key": re.compile(r"BEGIN PRIVATE KEY"),
    "Telegram bot token": re.compile(r"\b\d{8,12}:[A-Za-z0-9_-]{30,}\b"),
}


def fail(message: str) -> None:
    raise AssertionError(message)


def load_json(path: Path) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        fail(f"Invalid JSON: {path.relative_to(ROOT)}: {exc}")


def validate_workflow(path: Path) -> None:
    data = load_json(path)
    if not isinstance(data, dict):
        fail(f"Workflow must be an object: {path.name}")
    nodes = data.get("nodes")
    connections = data.get("connections")
    if not isinstance(nodes, list) or not nodes:
        fail(f"Workflow has no nodes: {path.name}")
    if not isinstance(connections, dict):
        fail(f"Workflow has invalid connections: {path.name}")

    names = [node.get("name") for node in nodes]
    if len(names) != len(set(names)):
        fail(f"Duplicate node names: {path.name}")
    if any(not name for name in names):
        fail(f"Unnamed node: {path.name}")

    known = set(names)
    for source, groups in connections.items():
        if source not in known:
            fail(f"Unknown connection source {source!r}: {path.name}")
        for outputs in groups.values():
            for output in outputs:
                for target in output:
                    if target["node"] not in known:
                        fail(f"Unknown connection target {target['node']!r}: {path.name}")

    credential_refs = [node["name"] for node in nodes if node.get("credentials")]
    if credential_refs:
        fail(f"Credential references must be removed: {credential_refs}")


def validate_fixtures() -> None:
    required = {"name", "email", "message", "source", "consent_to_contact", "idempotency_key"}
    label_tokens = {"hot", "warm", "cold", "review", "invalid", "consent", "injection"}
    keys: set[str] = set()
    for path in sorted(FIXTURES.glob("*.json")):
        if any(token in path.stem.lower() for token in label_tokens):
            fail(f"Fixture filename leaks its test class: {path.name}")
        data = load_json(path)
        if not isinstance(data, dict):
            fail(f"Fixture must be an object: {path.name}")
        missing = required - data.keys()
        if missing:
            fail(f"Fixture {path.name} missing: {sorted(missing)}")
        key = str(data["idempotency_key"])
        if any(token in key.lower() for token in label_tokens):
            fail(f"Fixture idempotency key leaks its test class: {key}")
        if key in keys:
            fail(f"Duplicate fixture idempotency key: {key}")
        source = str(data["source"]).lower()
        if any(token in source for token in {"security", "injection", "prompt"}):
            fail(f"Fixture source leaks its test purpose: {data['source']}")
        keys.add(key)
    if len(keys) < 6:
        fail("Expected at least six demo fixtures")

    expected = load_json(ROOT / "demo" / "evaluation-cases.json")
    if not isinstance(expected, list) or len(expected) < 5:
        fail("Expected at least five AI extraction examples")
    known_fixtures = {path.name for path in FIXTURES.glob("*.json")}
    for case in expected:
        if case.get("fixture") not in known_fixtures:
            fail(f"Expected AI case references unknown fixture: {case.get('fixture')}")


def validate_sheet() -> None:
    path = ROOT / "demo" / "google-sheets-template.csv"
    with path.open(newline="", encoding="utf-8") as handle:
        headers = next(csv.reader(handle))
    if headers != EXPECTED_HEADERS:
        fail("Google Sheets header does not match the workflow audit contract")


def validate_extraction_contract() -> None:
    workflow = load_json(WORKFLOWS / "lead-routing-main.json")
    if not isinstance(workflow, dict):
        fail("Main workflow must be an object")
    extractor = next(
        (node for node in workflow.get("nodes", []) if node.get("name") == "Extract Lead Signals"),
        None,
    )
    if extractor is None:
        fail("Extract Lead Signals node is missing")

    try:
        embedded = json.loads(extractor["parameters"]["inputSchema"])
    except (KeyError, TypeError, json.JSONDecodeError) as exc:
        fail(f"Embedded extraction schema is invalid: {exc}")

    documented = load_json(ROOT / "schemas" / "lead-extraction.schema.json")
    if not isinstance(documented, dict):
        fail("Documented extraction schema must be an object")
    documented = {
        key: value
        for key, value in documented.items()
        if key not in {"$schema", "$id", "title"}
    }
    if embedded != documented:
        fail("Embedded extraction schema does not match schemas/lead-extraction.schema.json")


def scan_secrets() -> None:
    for path in ROOT.rglob("*"):
        ignored_directories = {".git", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"}
        if (
            not path.is_file()
            or any(part in ignored_directories for part in path.parts)
            or path.suffix in {".zip", ".pyc", ".pyo"}
        ):
            continue
        if path.resolve() == Path(__file__).resolve():
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for label, pattern in SECRET_PATTERNS.items():
            if pattern.search(text):
                fail(f"Possible {label} in {path.relative_to(ROOT)}")


def main() -> int:
    for path in sorted(WORKFLOWS.glob("*.json")):
        validate_workflow(path)
    load_json(ROOT / "schemas" / "lead-extraction.schema.json")
    validate_fixtures()
    validate_sheet()
    validate_extraction_contract()
    scan_secrets()
    print("All artifact checks passed.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except AssertionError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
