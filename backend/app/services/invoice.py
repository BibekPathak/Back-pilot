"""Invoice extraction service.

Given an invoice (structured dict or PDF file), extract the four required
fields.  The component is deliberately simple and replaceable — the
interesting part of BackPilot is browser execution/recovery, not document
intelligence.

Usage::

    # From structured input (dict / JSON).
    data = extract_invoice({"invoice_number": "INV-29381", ...})

    # From a PDF file.
    data = extract_invoice({}, pdf_path="/path/to/invoice.pdf")
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator


class InvoiceData(BaseModel):
    """The four fields every invoice form requires."""

    invoice_number: str = Field(..., min_length=1, description="Invoice identifier")
    vendor: str = Field(..., min_length=1, description="Vendor / supplier name")
    amount: float = Field(..., gt=0, description="Invoice amount (positive)")
    invoice_date: str = Field(
        ..., pattern=r"^\d{4}-\d{2}-\d{2}$",
        description="Date in YYYY-MM-DD format",
    )
    filename: str = Field("invoice.pdf", description="Original filename for upload")

    @field_validator("amount", mode="before")
    @classmethod
    def coerce_amount(cls, v: Any) -> float:
        if isinstance(v, str):
            v = v.replace(",", "").strip()
            return float(v)
        return float(v)


class ExtractionError(Exception):
    """Raised when required fields cannot be extracted."""


# ------------------------------------------------------------------
# Structured extraction (dict → InvoiceData)
# ------------------------------------------------------------------
_REQUIRED_FIELDS = ("invoice_number", "vendor", "amount", "invoice_date")
_OPTIONAL_FIELDS = ("filename",)


def _from_dict(raw: dict[str, Any]) -> InvoiceData:
    """Build InvoiceData from a plain dict, validating every field."""
    missing = [f for f in _REQUIRED_FIELDS if f not in raw or raw[f] is None]
    if missing:
        raise ExtractionError(f"Missing required fields: {', '.join(missing)}")
    filtered = {k: v for k, v in raw.items() if k in _REQUIRED_FIELDS + _OPTIONAL_FIELDS}
    return InvoiceData(**filtered)


# ------------------------------------------------------------------
# PDF text extraction (lightweight, pypdf)
# ------------------------------------------------------------------
# Patterns tuned for the demo invoice; replaceable with a real parser.
_INV_NUM_PATTERNS = [
    re.compile(r"(?:invoice|inv)\s*(?:#|no\.?|number)?\s*[:\-]?\s*([A-Z0-9\-]+)", re.I),
    re.compile(r"([A-Z]{2,3}-\d{4,6})"),
]
_VENDOR_PATTERNS = [
    re.compile(r"(?:vendor|supplier|bill\s*to|from)\s*[:\-]?\s*(.+)", re.I),
]
_AMOUNT_PATTERNS = [
    re.compile(r"(?:total|amount|balance\s*due)\s*[:\-]?\s*\$?\s*([\d,]+\.?\d*)", re.I),
]
_DATE_PATTERNS = [
    re.compile(r"(?:date|invoice\s*date|issued)\s*[:\-]?\s*(\d{4}-\d{2}-\d{2})", re.I),
    re.compile(r"(\d{2}/\d{2}/\d{4})"),
]


def _first_match(text: str, patterns: list[re.Pattern]) -> str | None:
    for p in patterns:
        m = p.search(text)
        if m:
            return m.group(1).strip()
    return None


def _extract_from_pdf_text(text: str) -> dict[str, str]:
    result: dict[str, str] = {}
    inv = _first_match(text, _INV_NUM_PATTERNS)
    if inv:
        result["invoice_number"] = inv
    vendor = _first_match(text, _VENDOR_PATTERNS)
    if vendor:
        result["vendor"] = vendor
    amount = _first_match(text, _AMOUNT_PATTERNS)
    if amount:
        result["amount"] = amount
    date = _first_match(text, _DATE_PATTERNS)
    if date:
        result["invoice_date"] = date
    return result


def _from_pdf(pdf_path: str | Path) -> InvoiceData:
    """Extract InvoiceData from a PDF via pypdf text extraction + regex."""
    try:
        from pypdf import PdfReader
    except ImportError:
        raise ExtractionError("pypdf is required for PDF extraction")

    path = Path(pdf_path)
    if not path.exists():
        raise ExtractionError(f"PDF not found: {path}")
    reader = PdfReader(str(path))
    full_text = "\n".join(page.extract_text() or "" for page in reader.pages)
    if not full_text.strip():
        raise ExtractionError("PDF contains no extractable text")

    fields = _extract_from_pdf_text(full_text)
    fields["filename"] = path.name
    missing = [f for f in _REQUIRED_FIELDS if f not in fields]
    if missing:
        raise ExtractionError(
            f"Could not extract fields from PDF: {', '.join(missing)}. "
            f"Raw text preview: {full_text[:300]!r}"
        )
    return InvoiceData(**fields)


# ------------------------------------------------------------------
# Public API
# ------------------------------------------------------------------
def extract_invoice(
    raw: dict[str, Any] | None = None,
    *,
    pdf_path: str | Path | None = None,
) -> InvoiceData:
    """Extract invoice data from structured input or a PDF.

    Priority:
    1. If *raw* has all required fields → use it directly.
    2. If *pdf_path* is given → attempt PDF text extraction.
    3. Otherwise → ``ExtractionError``.
    """
    if raw and all(f in raw for f in _REQUIRED_FIELDS):
        return _from_dict(raw)
    if pdf_path:
        return _from_pdf(pdf_path)
    if raw:
        return _from_dict(raw)
    raise ExtractionError("No invoice data provided")
