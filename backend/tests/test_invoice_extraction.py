"""Tests for the invoice extraction service."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.invoice import ExtractionError, InvoiceData, extract_invoice


# ------------------------------------------------------------------
# Structured extraction
# ------------------------------------------------------------------
def test_extract_from_dict():
    data = extract_invoice({
        "invoice_number": "INV-29381",
        "vendor": "Acme Corp",
        "amount": 4291.20,
        "invoice_date": "2026-09-05",
    })
    assert data.invoice_number == "INV-29381"
    assert data.vendor == "Acme Corp"
    assert data.amount == 4291.20
    assert data.invoice_date == "2026-09-05"
    assert data.filename == "invoice.pdf"


def test_extract_from_dict_with_filename():
    data = extract_invoice({
        "invoice_number": "INV-100",
        "vendor": "Widget Inc",
        "amount": 99.99,
        "invoice_date": "2026-01-01",
        "filename": "custom.pdf",
    })
    assert data.filename == "custom.pdf"


def test_extract_string_amount():
    data = extract_invoice({
        "invoice_number": "INV-200",
        "vendor": "Big Co",
        "amount": "1,234.56",
        "invoice_date": "2026-03-15",
    })
    assert data.amount == 1234.56


def test_extract_missing_field_raises():
    with pytest.raises(ExtractionError, match="Missing required fields"):
        extract_invoice({"invoice_number": "INV-300", "vendor": "X"})


def test_extract_nothing_raises():
    with pytest.raises(ExtractionError, match="No invoice data"):
        extract_invoice()


# ------------------------------------------------------------------
# PDF extraction
# ------------------------------------------------------------------
def test_extract_from_pdf(tmp_path):
    # Create a valid minimal PDF with extractable text.
    pdf_content = b"""%PDF-1.4
1 0 obj
<< /Type /Catalog /Pages 2 0 R >>
endobj

2 0 obj
<< /Type /Pages /Kids [3 0 R] /Count 1 >>
endobj

3 0 obj
<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>
endobj

4 0 obj
<< /Length 250 >>
stream
BT
/F1 14 Tf
50 750 Td
(Invoice Number: INV-PDF-001) Tj
0 -25 Td
(Vendor: PDF Test Corp) Tj
0 -25 Td
(Amount: 999.99) Tj
0 -25 Td
(Invoice Date: 2026-07-04) Tj
ET
endstream
endobj

5 0 obj
<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>
endobj

xref
0 6
0000000000 65535 f 
0000000009 00000 n 
0000000058 00000 n 
0000000115 00000 n 
0000000266 00000 n 
0000000568 00000 n 

trailer
<< /Size 6 /Root 1 0 R >>

startxref
647
%%EOF
"""
    pdf_path = tmp_path / "test_invoice.pdf"
    pdf_path.write_bytes(pdf_content)
    data = extract_invoice(pdf_path=str(pdf_path))
    assert data.invoice_number == "INV-PDF-001"
    assert data.vendor == "PDF Test Corp"
    assert data.amount == 999.99
    assert data.invoice_date == "2026-07-04"
    assert data.filename == "test_invoice.pdf"


def test_extract_pdf_not_found():
    with pytest.raises(ExtractionError, match="PDF not found"):
        extract_invoice(pdf_path="/nonexistent/invoice.pdf")


# ------------------------------------------------------------------
# Pydantic model
# ------------------------------------------------------------------
def test_invoice_data_validation():
    data = InvoiceData(
        invoice_number="INV-99",
        vendor="Test Co",
        amount=50.00,
        invoice_date="2026-12-31",
    )
    assert data.amount == 50.00


def test_invoice_data_rejects_negative():
    with pytest.raises(Exception):
        InvoiceData(
            invoice_number="INV-X",
            vendor="Bad",
            amount=-100,
            invoice_date="2026-01-01",
        )


def test_invoice_data_rejects_bad_date():
    with pytest.raises(Exception):
        InvoiceData(
            invoice_number="INV-X",
            vendor="Bad",
            amount=100,
            invoice_date="01/01/2026",
        )
