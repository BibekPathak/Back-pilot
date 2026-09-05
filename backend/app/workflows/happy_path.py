"""Hard-coded happy-path invoice workflow.

Proves the full pipeline: extract → navigate → login → fill → upload →
submit → verify.  No LLM involved.  Deterministic and reproducible.

Usage::

    from app.workflows.happy_path import run_happy_path
    result = await run_happy_path(
        executor,
        invoice_data={"invoice_number": "INV-29381", ...},
        portal_url="http://localhost:8081",
    )
    assert result.success
"""

from __future__ import annotations

from typing import Any, Optional

from app.browser.actions import AgentAction, Click, Goto, Type, Upload, Wait, Finish, Target
from app.browser.executor import BrowserExecutor
from app.browser.observation import PageObservation
from app.services.invoice import InvoiceData, extract_invoice
from app.workflows.engine import RunResult, WorkflowEngine


def _build_steps(invoice: InvoiceData, portal_url: str) -> list[AgentAction]:
    """Build the deterministic sequence of actions for the happy path."""
    base = portal_url.rstrip("/")
    return [
        # 1. Navigate to portal login
        Goto(url=f"{base}/login", description="navigate to login page"),

        # 2. Fill username
        Type(
            target=Target(label="Username:"),
            text="admin",
            description="enter username",
        ),

        # 3. Fill password
        Type(
            target=Target(label="Password:"),
            text="admin",
            description="enter password",
        ),

        # 4. Click login
        Click(
            target=Target(label="LOGIN"),
            description="submit login form",
        ),

        # 5. Wait for navigation
        Wait(ms=500, description="wait for login redirect"),

        # 6. Navigate to invoice page
        Goto(url=f"{base}/invoices", description="navigate to invoice processing"),

        # 7. Fill invoice number
        Type(
            target=Target(label="Invoice Number:"),
            text=invoice.invoice_number,
            description="enter invoice number",
        ),

        # 8. Fill vendor
        Type(
            target=Target(label="Vendor:"),
            text=invoice.vendor,
            description="enter vendor name",
        ),

        # 9. Fill amount
        Type(
            target=Target(label="Amount:"),
            text=str(invoice.amount),
            description="enter invoice amount",
        ),

        # 10. Fill date
        Type(
            target=Target(label="Invoice Date:"),
            text=invoice.invoice_date,
            description="enter invoice date",
        ),

        # 11. Upload document
        Upload(
            target=Target(label="Document:"),
            filepath=invoice.filename,
            description="upload invoice PDF",
        ),

        # 12. Submit form
        Click(
            target=Target(label="SAVE & CONTINUE"),
            description="submit invoice form",
        ),

        # 13. Wait for submission
        Wait(ms=500, description="wait for submission redirect"),

        # 14. Finish
        Finish(description="invoice submitted"),
    ]


async def run_happy_path(
    executor: BrowserExecutor,
    *,
    invoice_data: dict[str, Any] | InvoiceData | None = None,
    pdf_path: str | None = None,
    portal_url: str = "http://localhost:8081",
    max_steps: int = 100,
) -> RunResult:
    """Run the hard-coded happy-path workflow.

    Parameters
    ----------
    executor:
        A live :class:`BrowserExecutor` pointed at the portal.
    invoice_data:
        Structured invoice dict or :class:`InvoiceData`.  If ``None``, a
        default fixture is used.
    pdf_path:
        Optional path to a PDF for extraction.
    portal_url:
        Base URL of the legacy portal.
    max_steps:
        Hard cap on workflow steps.

    Returns
    -------
    RunResult with ``state == "SUCCESS"`` on success.
    """
    if invoice_data is None:
        invoice_data = {
            "invoice_number": "INV-29381",
            "vendor": "Acme Corp",
            "amount": 4291.20,
            "invoice_date": "2026-09-05",
            "filename": "fixtures/invoice.pdf",
        }

    if isinstance(invoice_data, InvoiceData):
        invoice = invoice_data
    else:
        invoice = extract_invoice(invoice_data, pdf_path=pdf_path)

    steps = _build_steps(invoice, portal_url)
    engine = WorkflowEngine(executor, max_steps=max_steps)
    return await engine.run(steps)
