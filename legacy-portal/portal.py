"""ACME ENTERPRISE RESOURCE PORTAL — legacy ERP simulator.

Deliberately ugly, deterministic, and able to inject realistic back-office
failures so the BackPilot agent has something messy to recover from.
"""

from __future__ import annotations

import os
import time
from pathlib import Path

import uvicorn
from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from failure import FailureInjector, WORKFLOW_STEPS

BASE_DIR = Path(__file__).resolve().parent

app = FastAPI(title="ACME Legacy ERP Portal")
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

USERNAME = "admin"
PASSWORD = "admin"

_SESSIONS: dict[str, dict] = {}
_session_counter = 0
MAX_UPLOAD_BYTES = 5 * 1024 * 1024

BASE_FIELDS = {
    "invoice_number": "Invoice Number",
    "vendor": "Vendor",
    "amount": "Amount",
    "invoice_date": "Invoice Date",
}
CHANGED_FIELDS = {
    "invoice_number": "Document ID",
    "vendor": "Supplier Name",
    "amount": "Total Value",
    "invoice_date": "Issue Date",
}


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------
def injector_for(request: Request) -> FailureInjector:
    scenario = request.query_params.get("scenario")
    if not scenario:
        sess = session(request)
        if sess and sess.get("scenario"):
            scenario = sess["scenario"]
    return FailureInjector(mode=scenario) if scenario else FailureInjector.from_env()


def _new_session() -> str:
    global _session_counter
    _session_counter += 1
    sid = f"sess_{_session_counter}"
    _SESSIONS[sid] = {
        "user": None,
        "scenario": None,
        "expired": False,
        "submitted": False,
    }
    return sid


def session(request: Request) -> dict | None:
    sid = request.cookies.get("bp_session")
    return _SESSIONS.get(sid) if sid else None


def render(request: Request, template: str, **ctx):
    import datetime
    ctx.setdefault("now", datetime.datetime.now().strftime("%m/%d/%Y %I:%M:%S %p"))
    return templates.TemplateResponse(request, template, ctx)


def _slow(seconds: float = 3.0):
    time.sleep(seconds)


def _labels(selector_changed: bool) -> dict:
    return CHANGED_FIELDS if selector_changed else BASE_FIELDS


# --------------------------------------------------------------------------
# Auth
# --------------------------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
def root(request: Request):
    return RedirectResponse("/dashboard" if session(request) else "/login", status_code=302)


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request, error: str = ""):
    return render(request, "login.html", error=error)


@app.post("/login")
def login_post(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
):
    if injector_for(request).applies("LOGIN_POST", {"SLOW_NETWORK"}):
        _slow()

    if username != USERNAME or password != PASSWORD:
        return render(request, "login.html", error="Invalid credentials")

    response = RedirectResponse("/invoices", status_code=302)
    sid = _new_session()
    _SESSIONS[sid]["user"] = username
    _SESSIONS[sid]["scenario"] = injector_for(request).mode
    response.set_cookie("bp_session", sid, httponly=True, samesite="lax")
    return response


@app.get("/logout")
def logout(request: Request):
    sid = request.cookies.get("bp_session")
    if sid:
        _SESSIONS.pop(sid, None)
    response = RedirectResponse("/login", status_code=302)
    response.delete_cookie("bp_session")
    return response


# --------------------------------------------------------------------------
# Dashboard
# --------------------------------------------------------------------------
@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request):
    sess = session(request)
    if sess is None:
        return RedirectResponse("/login", status_code=302)
    return render(request, "dashboard.html", user=sess["user"], submitted=sess["submitted"])


# --------------------------------------------------------------------------
# Invoice processing
# --------------------------------------------------------------------------
@app.get("/invoices", response_class=HTMLResponse)
def invoices_page(request: Request, next: str = ""):
    return _invoice_page(request, next=next)


def _invoice_page(request: Request, next: str = "") -> HTMLResponse:
    sess = session(request)
    if sess is None:
        return RedirectResponse("/login", status_code=302)

    inj = injector_for(request)

    if inj.applies("INVOICE_PAGE", {"SLOW_NETWORK"}):
        _slow()

    # The session has been marked expired by a prior visit under SESSION_EXPIRED.
    if sess["expired"]:
        sess.pop("bp_session", None)
        _SESSIONS.pop(request.cookies["bp_session"], None)
        response = RedirectResponse("/login?error=session-expired", status_code=302)
        response.delete_cookie("bp_session")
        return response

    # Inject session expiration while viewing the invoice page.
    if inj.applies("INVOICE_PAGE", {"SESSION_EXPIRED"}):
        sess["expired"] = True
        _SESSIONS.pop(request.cookies["bp_session"], None)
        response = RedirectResponse("/login?error=session-expired", status_code=302)
        response.delete_cookie("bp_session")
        return response

    selector_changed = inj.applies("FILL_FORM", {"SELECTOR_CHANGE"})
    captcha = inj.applies("FILL_FORM", {"CAPTCHA"})
    missing_submit = inj.applies("SUBMIT", {"MISSING_ELEMENT"})
    modal = inj.applies("INVOICE_PAGE", {"UNEXPECTED_MODAL"})

    return render(
        request,
        "invoices.html",
        labels=_labels(selector_changed),
        missing_submit=missing_submit,
        captcha=captcha,
        modal=modal,
        error=next,
        scenario=request.query_params.get("scenario", ""),
    )


@app.post("/invoices")
async def invoices_post(
    request: Request,
    invoice_number: str = Form(""),
    vendor: str = Form(""),
    amount: str = Form(""),
    invoice_date: str = Form(""),
    captcha_answer: str = Form(""),
    document: UploadFile | None = File(None),
):
    sess = session(request)
    if sess is None:
        return RedirectResponse("/login", status_code=302)

    inj = injector_for(request)

    if inj.applies("UPLOAD", {"UPLOAD_FAILURE"}) or inj.applies("SUBMIT", {"UPLOAD_FAILURE"}):
        return _invoice_page(request, next="Upload service unavailable (UPLOAD_FAILURE)")

    if inj.applies("FILL_FORM", {"CAPTCHA"}) and captcha_answer != "7":
        return _invoice_page(request, next="Captcha verification failed: wrong answer")

    if not invoice_number or not vendor or not amount:
        return _invoice_page(request, next="Please fill in all required fields.")

    if document is not None:
        data = await document.read()
        if len(data) > MAX_UPLOAD_BYTES:
            return _invoice_page(request, next="File too large (max 5 MB)")
        if document.filename and not document.filename.endswith(".pdf"):
            return _invoice_page(request, next="Only .pdf files are accepted")

    sess["submitted"] = True
    return RedirectResponse("/success", status_code=302)


# --------------------------------------------------------------------------
# Success
# --------------------------------------------------------------------------
@app.get("/success", response_class=HTMLResponse)
def success(request: Request):
    sess = session(request)
    if sess is None:
        return RedirectResponse("/login", status_code=302)
    if not sess["submitted"]:
        return RedirectResponse("/invoices", status_code=302)
    return render(request, "success.html", user=sess["user"])


@app.get("/health")
def health():
    return {"status": "ok"}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8081")))
