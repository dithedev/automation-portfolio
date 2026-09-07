from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


OUTPUT_DIR = Path(__file__).resolve().parents[1] / "demo" / "invoices"


@dataclass(frozen=True)
class Invoice:
    filename: str
    number: str | None
    subtotal: Decimal
    tax: Decimal
    total: Decimal


INVOICES = (
    Invoice(
        filename="invoice-001.pdf",
        number="ACME-2026-0042",
        subtotal=Decimal("1000.00"),
        tax=Decimal("210.00"),
        total=Decimal("1210.00"),
    ),
    Invoice(
        filename="invoice-002.pdf",
        number=None,
        subtotal=Decimal("480.00"),
        tax=Decimal("100.80"),
        total=Decimal("580.80"),
    ),
    Invoice(
        filename="invoice-003.pdf",
        number="ACME-2026-0044",
        subtotal=Decimal("700.00"),
        tax=Decimal("147.00"),
        total=Decimal("900.00"),
    ),
)


def money(value: Decimal) -> str:
    return f"{value:,.2f} EUR"


def build_invoice(invoice: Invoice) -> None:
    output_path = OUTPUT_DIR / invoice.filename
    styles = getSampleStyleSheet()
    styles.add(
        ParagraphStyle(
            name="InvoiceRight",
            parent=styles["BodyText"],
            alignment=TA_RIGHT,
            leading=16,
        )
    )
    document = SimpleDocTemplate(
        str(output_path),
        pagesize=A4,
        rightMargin=20 * mm,
        leftMargin=20 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        # Keep PDF metadata neutral. The extraction model should rely only on
        # the visible document content, not on a semantic title or author hint.
        title="",
        author="",
    )

    story = [
        Table(
            [
                [
                    Paragraph("<b>ACME Automation Labs</b><br/>Konstitucijos pr. 1<br/>Vilnius, Lithuania", styles["BodyText"]),
                    Paragraph("<font size=22><b>INVOICE</b></font>", styles["InvoiceRight"]),
                ]
            ],
            colWidths=[100 * mm, 55 * mm],
        ),
        Spacer(1, 12 * mm),
    ]

    details = [
        ["Invoice number", invoice.number or ""],
        ["Invoice date", "2026-08-15"],
        ["Due date", "2026-08-29"],
        ["Currency", "EUR"],
        ["Customer", "Northstar Demo Company"],
    ]
    details_table = Table(details, colWidths=[45 * mm, 110 * mm])
    details_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#EFF3F8")),
                ("TEXTCOLOR", (0, 0), (0, -1), colors.HexColor("#334155")),
                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
                ("PADDING", (0, 0), (-1, -1), 7),
            ]
        )
    )
    story.extend([details_table, Spacer(1, 12 * mm)])

    line_items = [
        ["Description", "Qty", "Unit price", "Amount"],
        ["Workflow architecture and implementation", "1", money(invoice.subtotal), money(invoice.subtotal)],
    ]
    items_table = Table(line_items, colWidths=[82 * mm, 18 * mm, 28 * mm, 28 * mm])
    items_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1E3A5F")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("ALIGN", (1, 1), (-1, -1), "RIGHT"),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
                ("PADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    story.extend([items_table, Spacer(1, 8 * mm)])

    totals = [
        ["Subtotal", money(invoice.subtotal)],
        ["VAT 21%", money(invoice.tax)],
        ["Total", money(invoice.total)],
    ]
    totals_table = Table(totals, colWidths=[35 * mm, 35 * mm], hAlign="RIGHT")
    totals_table.setStyle(
        TableStyle(
            [
                ("ALIGN", (0, 0), (-1, -1), "RIGHT"),
                ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
                ("LINEABOVE", (0, -1), (-1, -1), 1, colors.HexColor("#1E3A5F")),
                ("PADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    story.extend(
        [
            totals_table,
            Spacer(1, 18 * mm),
            Paragraph("Payment details", styles["Heading3"]),
            Paragraph("IBAN: LT00 0000 0000 0000 0000<br/>Payment reference: invoice number", styles["BodyText"]),
        ]
    )
    document.build(story)


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for invoice in INVOICES:
        build_invoice(invoice)
        print(f"Created {invoice.filename}")


if __name__ == "__main__":
    main()
