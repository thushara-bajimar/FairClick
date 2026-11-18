"""Drive the real FairClick dashboard with Playwright and capture screenshots.

This is both a UI end-to-end check (tasks are started through the form and
approved/rejected with the on-screen buttons) and the source of the
application screenshots used in the report. Requires the app running:

    python run.py          # in another terminal
    python scripts/capture_screenshots.py [--base http://127.0.0.1:8000]
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from playwright.sync_api import Page, expect, sync_playwright

OUT = Path(__file__).resolve().parent.parent / "docs" / "screenshots"


def shot(page: Page, name: str, full_page: bool = True) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    page.wait_for_timeout(600)
    page.screenshot(path=str(OUT / f"{name}.png"), full_page=full_page)
    print("  saved", name)


def start_task(page: Page, base: str, task_title: str, site_name: str, demo: bool) -> None:
    page.goto(f"{base}/app/new")
    page.get_by_role("radio", name=task_title).click()
    page.get_by_role("radio", name=site_name).click()
    if demo:
        page.get_by_text("Fill with the simulated demo account's details").click()
    page.get_by_role("button", name="Start agent").click()
    page.wait_for_url("**/app/sessions/*")


def wait_for_approval_panel(page: Page, timeout_s: int = 150) -> None:
    expect(page.get_by_text("Your approval is required")).to_be_visible(timeout=timeout_s * 1000)


def wait_for_finish(page: Page, timeout_s: int = 150) -> str:
    """Read the session status pill in the page header until the session ends."""
    deadline = time.time() + timeout_s
    pill = page.locator("main span.rounded-full.capitalize").first
    while time.time() < deadline:
        status = pill.inner_text().strip().lower()
        if status in ("completed", "rejected", "failed", "needs info", "stopped"):
            return status
        page.wait_for_timeout(500)
    raise TimeoutError("session did not finish")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://127.0.0.1:8000")
    base = parser.parse_args().base

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        page.set_default_timeout(20000)

        print("landing + new task")
        page.goto(base + "/")
        shot(page, "01_landing")
        page.goto(base + "/app/new")
        page.get_by_role("radio", name="Request refund").click()
        page.get_by_text("Fill with the simulated demo account's details").click()
        shot(page, "03_new_task")

        print("cancel StreamPlus (approve via UI)")
        start_task(page, base, "Cancel subscription", "StreamPlus", demo=False)
        wait_for_approval_panel(page)
        shot(page, "04_workspace_pending_approval")
        page.get_by_role("button", name="Approve and submit").click()
        assert wait_for_finish(page) == "completed"
        shot(page, "05_workspace_completed")

        print("refund ShopEase")
        start_task(page, base, "Request refund", "ShopEase", demo=True)
        wait_for_approval_panel(page)
        shot(page, "06_refund_approval", full_page=False)
        page.get_by_role("button", name="Approve and submit").click()
        assert wait_for_finish(page) == "completed"

        print("claim TravelQuick")
        start_task(page, base, "Claim compensation", "TravelQuick", demo=True)
        wait_for_approval_panel(page)
        page.get_by_role("button", name="Approve and submit").click()
        assert wait_for_finish(page) == "completed"
        page.get_by_text("Prepared summary document").click()
        shot(page, "07_claim_completed")

        print("reject tracking CookieWorld")
        start_task(page, base, "Reject non-essential tracking", "CookieWorld", demo=False)
        wait_for_approval_panel(page)
        page.get_by_role("button", name="Approve and submit").click()
        assert wait_for_finish(page) == "completed"

        print("dispute FitLife")
        start_task(page, base, "Dispute a charge", "FitLife", demo=True)
        wait_for_approval_panel(page)
        page.get_by_role("button", name="Approve and submit").click()
        assert wait_for_finish(page) == "completed"

        print("cancel FitLife (REJECT via UI)")
        start_task(page, base, "Cancel subscription", "FitLife", demo=False)
        wait_for_approval_panel(page)
        page.get_by_label("Note (optional, stored with your decision)").fill("Changed my mind - keep the plan for now.")
        page.get_by_role("button", name="Reject").click()
        assert wait_for_finish(page) == "rejected"
        shot(page, "08_workspace_rejected", full_page=False)

        print("dashboard, evidence, reports, settings")
        page.goto(base + "/app")
        shot(page, "02_dashboard")
        page.goto(base + "/app/evidence")
        shot(page, "09_evidence_vault", full_page=False)
        page.locator("ul li button").first.click()
        shot(page, "10_evidence_detail", full_page=False)
        page.keyboard.press("Escape")
        page.goto(base + "/app/reports")
        shot(page, "11_reports")
        page.goto(base + "/app/settings")
        shot(page, "12_settings")

        print("simulated sites")
        for site in ("streamplus", "shopease", "cookieworld", "fitlife", "travelquick"):
            page.goto(f"{base}/sites/{site}/index.html")
            page.wait_for_timeout(900)
            shot(page, f"site_{site}", full_page=False)
        page.goto(f"{base}/sites/streamplus/cancel/offer.html")
        shot(page, "site_streamplus_offer", full_page=False)

        mobile = browser.new_page(viewport={"width": 390, "height": 844})
        mobile.goto(base + "/app")
        shot(mobile, "13_dashboard_mobile", full_page=False)
        browser.close()
    print("done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
