"""FairClick benchmark: agent vs. manual baseline on all simulated interfaces.

Usage (from backend/):  python -m benchmark.run_benchmark [--repeats 3]

What is MEASURED (from real runs):
  * Agent: success, browser interactions, wall-clock time, detections, evidence,
    approval requests, and detection precision/recall against ground truth.
  * Manual baseline: the scripted path an informed human must take is *executed*
    in a real browser to verify it works and to count its interactions/obstacles.

What is ESTIMATED (not measured):
  * Manual completion TIME, using the Keystroke-Level Model (Card, Moran & Newell,
    1980). No human participants were timed.

The benchmark uses its own data directory (benchmark/data) so it does not mix
with interactive usage. Final approvals are given by the benchmark operator
(this script) and are recorded as such ("benchmark-operator").
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

BENCH_DIR = Path(__file__).resolve().parent
BACKEND_DIR = BENCH_DIR.parent
sys.path.insert(0, str(BACKEND_DIR))

DATA_DIR = BENCH_DIR / "data"
os.environ["FAIRCLICK_DATA_DIR"] = str(DATA_DIR)
os.environ.setdefault("FAIRCLICK_STEP_DELAY_MS", "0")
os.environ.setdefault("FAIRCLICK_HEADLESS", "true")

from app.devserver import free_port  # noqa: E402

PORT = free_port()
os.environ["FAIRCLICK_PORT"] = str(PORT)

from app import database as db  # noqa: E402
from app.agents import orchestrator  # noqa: E402
from app.config import settings  # noqa: E402
from app.devserver import ServerThread  # noqa: E402

GROUND_TRUTH = json.loads((BENCH_DIR / "ground_truth.json").read_text(encoding="utf-8"))

SCENARIOS = [
    {"id": "cancel-streamplus", "task_type": "cancel_subscription", "site_id": "streamplus", "inputs": {}},
    {"id": "cancel-fitlife", "task_type": "cancel_subscription", "site_id": "fitlife", "inputs": {}},
    {"id": "tracking-cookieworld", "task_type": "reject_tracking", "site_id": "cookieworld", "inputs": {}},
    {"id": "tracking-shopease", "task_type": "reject_tracking", "site_id": "shopease", "inputs": {}},
    {"id": "refund-shopease", "task_type": "request_refund", "site_id": "shopease",
     "inputs": {"order_number": "ORD-1002", "reason": "Item arrived damaged", "details": "The left ear cup does not work."}},
    {"id": "dispute-fitlife", "task_type": "dispute_charge", "site_id": "fitlife",
     "inputs": {"transaction_id": "TXN-90545", "reason": "I did not authorise this charge", "details": "I never signed up for Coach+."}},
    {"id": "claim-travelquick", "task_type": "claim_compensation", "site_id": "travelquick",
     "inputs": {"booking_reference": "TQ7F3K", "flight_number": "TQ 482", "flight_date": "2026-10-28", "delay_hours": "4.2",
                "passenger_name": "Alex Morgan", "contact_email": "alex.morgan@example.com"}},
]

# Scripted manual paths: what an informed human has to do, including detours
# forced by the site (declining offers, surveys, hidden menus).
MANUAL_PATHS: dict[str, dict] = {
    "cancel-streamplus": {"success": "has been cancelled", "steps": [
        ("hover", ".avatar"), ("click_css", 'a[href="account.html"]'), ("click_text", "More membership options"),
        ("click_text", "Cancel membership"), ("click_text", "No thanks, I prefer losing all my benefits"),
        ("click_text", "I don't care about my watchlist"), ("click_text", "Continue to cancellation"),
        ("check", "Prefer not to say"), ("click_role", "Continue"), ("click_text", "Yes, continue cancellation"),
        ("click_role", "Cancel my membership")]},
    "cancel-fitlife": {"success": "has been turned off", "steps": [
        ("click_text", "Profile"), ("click_css", 'a[href="billing.html"]'), ("click_text", "Manage subscription"),
        ("click_css", 'a[href="cancel-step1.html"]'), ("click_text", "I'm okay losing my progress"),
        ("click_text", "No thanks, continue to cancel"), ("uncheck", "Keep my data with the Pro Lite add-on"),
        ("click_role", "Turn off auto-renewal")]},
    "tracking-cookieworld": {"success": "have been saved", "steps": [
        ("click_text", "Manage settings"), ("click_text", "More options"), ("click_role", "Reject all")]},
    "tracking-shopease": {"success": "have been saved", "steps": [
        ("click_text", "Manage options"), ("uncheck", "Analytics cookies"), ("uncheck", "Advertising cookies"),
        ("click_role", "Save preferences")]},
    "refund-shopease": {"success": "has been received", "steps": [
        ("click_css", 'a[href="account.html"]'), ("click_text", "Your Orders"), ("click_css", 'a[href="order.html?id=ORD-1002"]'),
        ("click_text", "Get help with order"), ("click_text", "Request a refund"), ("check", "Prefer not to say"),
        ("click_role", "Continue to refund request"), ("fill", "Order number", "ORD-1002"),
        ("select", "Reason for refund", "damaged"), ("fill", "Details", "The left ear cup does not work."),
        ("check", "Original payment method"), ("uncheck", "Sign me up for ShopEase deals and offers"),
        ("click_role", "Submit refund request")]},
    "dispute-fitlife": {"success": "has been received", "steps": [
        ("click_text", "Profile"), ("click_css", 'a[href="billing.html"]'), ("click_text", "Report a problem with a charge"),
        ("click_text", "No, continue with dispute"), ("select", "Which charge?", "TXN-90545"),
        ("select", "Reason", "unauthorised"), ("fill", "What happened?", "I never signed up for Coach+."),
        ("check", "Refund to original payment method"), ("check", "I confirm the information above is accurate"),
        ("click_role", "Submit dispute")]},
    "claim-travelquick": {"success": "has been received", "steps": [
        ("click_text", "Manage trips"), ("click_text", "Trip details"), ("click_role", "Help ▾"), ("click_text", "FAQs"),
        ("click_text", "Delays and cancellations"), ("click_text", "submit a compensation claim"),
        ("click_text", "No thanks, continue to claim"), ("check", "Don't know"),
        ("select", "How did you hear about TravelQuick?", "other"), ("click_role", "Continue"),
        ("fill", "Booking reference", "TQ7F3K"), ("fill", "Flight number", "TQ 482"), ("fill", "Flight date", "2026-10-28"),
        ("select", "Arrival delay", "gt4"), ("fill", "Passenger full name", "Alex Morgan"),
        ("fill", "Contact email", "alex.morgan@example.com"), ("check", "Bank transfer"),
        ("uncheck", "Add priority claim processing"), ("uncheck", "I accept the voucher and waive any further claims"),
        ("check", "I confirm the information is accurate"), ("click_role", "Submit claim")]},
}

# Keystroke-Level Model operator times (seconds), Card, Moran & Newell (1980).
KLM = {"K": 0.28, "P": 1.1, "B": 0.2, "M": 1.35, "H": 0.4}


def klm_estimate(steps: list[tuple], pages: int) -> float:
    seconds = 0.0
    for step in steps:
        kind = step[0]
        if kind == "fill":
            seconds += KLM["M"] + KLM["P"] + KLM["B"] + KLM["H"] + KLM["K"] * len(step[2]) + KLM["H"]
        elif kind == "select":
            seconds += KLM["M"] + 2 * (KLM["P"] + KLM["B"])
        elif kind == "hover":
            seconds += KLM["M"] + KLM["P"]
        else:
            seconds += KLM["M"] + KLM["P"] + KLM["B"]
    seconds += pages * KLM["M"]  # orient on each new screen
    return round(seconds, 1)


def run_manual(browser, scenario: dict) -> dict:
    spec = MANUAL_PATHS[scenario["id"]]
    page = browser.new_page()
    page.set_default_timeout(5000)
    started = time.monotonic()
    paths = []
    page.on("framenavigated", lambda f: paths.append(f.url) if f == page.main_frame else None)
    page.goto(f"{settings.base_url}/sites/{scenario['site_id']}/index.html")
    error = None
    try:
        for step in spec["steps"]:
            kind, target = step[0], step[1]
            if kind == "hover":
                page.locator(target).first.hover()
            elif kind == "click_css":
                page.locator(target).first.click()
            elif kind == "click_text":
                page.get_by_text(target, exact=True).first.click()
            elif kind == "click_role":
                page.get_by_role("button", name=target).first.click()
            elif kind == "check":
                page.get_by_label(target).first.check()
            elif kind == "uncheck":
                page.get_by_label(target).first.uncheck()
            elif kind == "fill":
                page.get_by_label(target, exact=True).first.fill(step[2])
            elif kind == "select":
                page.get_by_label(target, exact=True).first.select_option(step[2])
            page.wait_for_load_state("domcontentloaded")
            page.wait_for_timeout(250)
        page.wait_for_timeout(400)
        success = spec["success"] in page.inner_text("body")
    except Exception as exc:  # noqa: BLE001
        success, error = False, f"{type(exc).__name__}: {exc}"[:300]
    distinct_pages = list(dict.fromkeys(u.split("?")[0].split("#")[0] for u in paths))
    page.close()
    gt_pages = GROUND_TRUTH.get(scenario["site_id"], {})
    obstacles = sum(1 for u in distinct_pages
                    if isinstance(gt_pages.get(u.split(f"/sites/{scenario['site_id']}/")[-1]), list))
    return {
        "success": success, "error": error, "interactions": len(spec["steps"]), "pages": len(distinct_pages),
        "obstacles_encountered": obstacles, "estimated_time_s": klm_estimate(spec["steps"], len(distinct_pages)),
        "script_execution_s": round(time.monotonic() - started, 2), "time_is_estimate": True,
    }


def run_agent(scenario: dict) -> dict:
    task_id = db.new_id("tsk_")
    db.insert("tasks", {"id": task_id, "user_id": db.DEFAULT_USER_ID, "task_type": scenario["task_type"],
                        "site_id": scenario["site_id"], "inputs_json": json.dumps(scenario["inputs"]), "status": "created",
                        "source": "benchmark", "created_at": db.utcnow(), "completed_at": None})
    session_id = orchestrator.start_session(task_id, {"step_delay_ms": 0, "headless": True})
    deadline = time.time() + 240
    while time.time() < deadline:
        for req in db.query("SELECT id FROM approval_requests WHERE session_id=? AND status='pending'", (session_id,)):
            orchestrator.broker.decide(req["id"], True, "benchmark-operator", "Automated approval by benchmark script")
        status = db.query_one("SELECT status FROM agent_sessions WHERE id=?", (session_id,))["status"]
        if status not in ("starting", "running", "awaiting_approval"):
            break
        time.sleep(0.2)
    orchestrator.wait_for_session(session_id, 30)
    result = db.query_one("SELECT * FROM task_results WHERE session_id=?", (session_id,)) or {}
    detections = db.query("SELECT category, page_path FROM detections WHERE session_id=?", (session_id,))
    visited = {r["page_url"].split("?")[0].split("#")[0] for r in db.query(
        "SELECT page_url FROM agent_actions WHERE session_id=? AND action_type='observe'", (session_id,))}
    incidents = db.query_one("SELECT COUNT(*) AS n FROM security_incidents WHERE session_id=?", (session_id,))["n"]
    blocked = db.query_one("SELECT COUNT(*) AS n FROM agent_actions WHERE session_id=? AND agent='safety' AND outcome='blocked'", (session_id,))["n"]
    return {"session_id": session_id, "outcome": result.get("outcome"), "success": bool(result.get("success")),
            "interactions": result.get("interactions"), "duration_s": result.get("duration_seconds"),
            "pages": result.get("pages_visited"), "detections": len(detections), "evidence": result.get("evidence_count"),
            "approvals": result.get("approvals_requested"), "security_incidents": incidents, "blocked_actions": blocked,
            "score": score_detections(scenario["site_id"], scenario["task_type"], detections, visited, bool(result.get("success")))}


def score_detections(site: str, task_type: str, detections: list[dict], visited_urls: set[str], completed: bool) -> dict:
    prefix = f"/sites/{site}/"
    truth = {p: c for p, c in GROUND_TRUTH.get(site, {}).items() if p != "session"}
    if completed:
        truth["session"] = GROUND_TRUTH.get(site, {}).get("session", {}).get(task_type, [])
    visited_pages = {u.split(prefix)[-1] for u in visited_urls if prefix in u} | ({"session"} if completed else set())
    expected = {(p, c) for p, cats in truth.items() if p in visited_pages for c in cats}
    predicted = {("session" if d["page_path"] == "session" else d["page_path"].split(prefix)[-1], d["category"]) for d in detections}
    tp = expected & predicted
    return {"expected": len(expected), "true_positives": len(tp), "false_positives": len(predicted - expected),
            "false_negatives": len(expected - predicted),
            "missed": sorted(f"{p}:{c}" for p, c in expected - predicted),
            "extra": sorted(f"{p}:{c}" for p, c in predicted - expected)}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repeats", type=int, default=3)
    args = parser.parse_args()

    if DATA_DIR.exists():
        shutil.rmtree(DATA_DIR)
    db.init_db()
    from playwright.sync_api import sync_playwright

    results = []
    with ServerThread(PORT):
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            for scenario in SCENARIOS:
                print(f"== {scenario['id']}")
                manual = run_manual(browser, scenario)
                print(f"   manual: success={manual['success']} interactions={manual['interactions']} est={manual['estimated_time_s']}s {manual['error'] or ''}")
                runs = []
                for i in range(args.repeats):
                    run = run_agent(scenario)
                    runs.append(run)
                    print(f"   agent run {i + 1}: {run['outcome']} interactions={run['interactions']} t={run['duration_s']}s "
                          f"detections={run['detections']} TP={run['score']['true_positives']}/{run['score']['expected']} FP={run['score']['false_positives']}")
                results.append({"scenario": scenario["id"], "task_type": scenario["task_type"], "site_id": scenario["site_id"],
                                "manual": manual, "agent_runs": runs})
            browser.close()

    all_runs = [r for s in results for r in s["agent_runs"]]
    tp = sum(r["score"]["true_positives"] for r in all_runs)
    fp = sum(r["score"]["false_positives"] for r in all_runs)
    fn = sum(r["score"]["false_negatives"] for r in all_runs)
    successes = [r for r in all_runs if r["success"]]
    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "repeats": args.repeats,
        "scenarios": len(SCENARIOS),
        "agent_runs": len(all_runs),
        "agent_success_rate": round(100 * len(successes) / len(all_runs), 1),
        "detection_rate": round(100 * tp / (tp + fn), 1) if tp + fn else None,
        "detection_precision": round(100 * tp / (tp + fp), 1) if tp + fp else None,
        "true_positives": tp, "false_positives": fp, "false_negatives": fn,
        "agent_avg_duration_s": round(statistics.mean(r["duration_s"] for r in successes), 2) if successes else None,
        "agent_avg_interactions": round(statistics.mean(r["interactions"] for r in successes), 1) if successes else None,
        "manual_success_rate": round(100 * sum(s["manual"]["success"] for s in results) / len(results), 1),
        "manual_avg_interactions": round(statistics.mean(s["manual"]["interactions"] for s in results), 1),
        "manual_avg_estimated_time_s": round(statistics.mean(s["manual"]["estimated_time_s"] for s in results), 1),
        "total_approvals_requested": sum(r["approvals"] or 0 for r in all_runs),
        "total_evidence": sum(r["evidence"] or 0 for r in all_runs),
        "total_security_incidents": sum(r["security_incidents"] for r in all_runs),
        "notes": [
            "Agent figures are measured from real Playwright runs against the local simulations.",
            "Manual interaction counts come from executing a scripted human path in a real browser.",
            "Manual times are KLM estimates (K=0.28s, P=1.1s, B=0.2s, M=1.35s, H=0.4s); no human participants were timed.",
            "Agent interactions include detours an agent makes while exploring; agent time excludes the time a human spends reviewing the approval request.",
            "Ground-truth labels were written by the FairClick developers who also built the detector, so detection figures are optimistic for unseen websites.",
        ],
    }
    out = {"summary": summary, "scenarios": [
        {**s, "agent_summary": {
            "success_rate": round(100 * sum(r["success"] for r in s["agent_runs"]) / len(s["agent_runs"]), 1),
            "avg_interactions": round(statistics.mean(r["interactions"] or 0 for r in s["agent_runs"]), 1),
            "avg_duration_s": round(statistics.mean(r["duration_s"] or 0 for r in s["agent_runs"]), 2),
            "avg_detections": round(statistics.mean(r["detections"] for r in s["agent_runs"]), 1),
            "approvals": s["agent_runs"][0]["approvals"],
        }} for s in results]}
    results_dir = BENCH_DIR / "results"
    results_dir.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    for name in ("latest.json", f"benchmark_{stamp}.json"):
        (results_dir / name).write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
