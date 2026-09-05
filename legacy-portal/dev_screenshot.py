"""Dev helper: screenshot the legacy portal pages for visual verification."""
import asyncio
import sys

from playwright.async_api import async_playwright

BASE = "http://127.0.0.1:8081"


async def main() -> None:
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        ctx = await browser.new_context()
        page = await ctx.new_page()
        await page.goto(f"{BASE}/login")
        await page.screenshot(path="/tmp/portal_login.png")
        await page.fill("#username", "admin")
        await page.fill("#password", "admin")
        await page.click("input[type=submit]")
        await page.wait_for_load_state("networkidle")
        # invoice page normal
        await page.screenshot(path="/tmp/portal_invoices_normal.png")
        # invoice page with captcha
        await page.goto(f"{BASE}/invoices?scenario=CAPTCHA")
        await page.wait_for_load_state("networkidle")
        await page.screenshot(path="/tmp/portal_invoices_captcha.png")
        # invoice page with modal
        await page.goto(f"{BASE}/login")
        await page.fill("#username", "admin")
        await page.fill("#password", "admin")
        await page.click("input[type=submit]")
        await page.goto(f"{BASE}/invoices?scenario=UNEXPECTED_MODAL")
        await page.wait_for_load_state("networkidle")
        await page.screenshot(path="/tmp/portal_invoices_modal.png")
        await browser.close()


asyncio.run(main())
