from __future__ import annotations

import csv
import json
from pathlib import Path

from pypdf import PdfReader


ROOT = Path(__file__).resolve().parents[1]


def validate_json_files() -> None:
    for path in sorted(ROOT.rglob("*.json")):
        with path.open("r", encoding="utf-8") as file:
            payload = json.load(file)
        if path.parent.name == "workflows":
            names = [node["name"] for node in payload["nodes"]]
            assert len(names) == len(set(names)), f"Duplicate node name in {path.name}"
            known = set(names)
            for source, groups in payload.get("connections", {}).items():
                assert source in known, f"Unknown connection source {source!r}"
                for outputs in groups.values():
                    for output in outputs:
                        for connection in output:
                            assert connection["node"] in known, (
                                f"Unknown connection target {connection['node']!r}"
                            )
        print(f"JSON OK: {path.relative_to(ROOT)}")


def validate_csv() -> None:
    path = ROOT / "demo" / "google-sheets-template.csv"
    with path.open("r", encoding="utf-8", newline="") as file:
        rows = list(csv.DictReader(file))
    assert rows, "Google Sheets template must contain an example row"
    assert "file_hash" in rows[0]
    assert "status" in rows[0]
    print("CSV OK: demo/google-sheets-template.csv")


def validate_pdfs() -> None:
    expected = {
        "invoice-001.pdf": ("ACME-2026-0042", "1,210.00 EUR"),
        "invoice-002.pdf": ("Invoice number", "580.80 EUR"),
        "invoice-003.pdf": ("ACME-2026-0044", "900.00 EUR"),
    }
    forbidden_hints = (
        "valid invoice",
        "missing invoice number",
        "mismatched totals",
        "not an invoice",
        "needs_review",
        "processed",
        "ai instruction",
        "system prompt",
    )

    for filename, fragments in expected.items():
        path = ROOT / "demo" / "invoices" / filename
        assert path.is_file(), f"Missing demo PDF: {filename}"
        reader = PdfReader(str(path))
        assert len(reader.pages) == 1, f"Expected one page in {filename}"
        text = reader.pages[0].extract_text() or ""
        for fragment in fragments:
            assert fragment in text, f"Missing {fragment!r} in {filename}"

        normalized_text = " ".join(text.lower().split())
        for hint in forbidden_hints:
            assert hint not in normalized_text, (
                f"Found test or AI hint {hint!r} in visible text of {filename}"
            )

        metadata = reader.metadata or {}
        assert not (metadata.get("/Title") or "").strip(), (
            f"PDF title metadata must be empty in {filename}"
        )
        assert not (metadata.get("/Author") or "").strip(), (
            f"PDF author metadata must be empty in {filename}"
        )
        print(f"PDF OK: demo/invoices/{filename}")


if __name__ == "__main__":
    validate_json_files()
    validate_csv()
    validate_pdfs()
