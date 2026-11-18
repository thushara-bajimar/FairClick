"""End-to-end tests: the real multi-agent system driving Chromium against the simulations."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app import database as db
from app.agents.navigator import BrowserNavigationAgent, NavigationError
from app.config import settings

from .conftest import run_task

WORKFLOWS = [
    ("cancel_subscription", "streamplus", {}),
    ("cancel_subscription", "fitlife", {}),
    ("reject_tracking", "cookieworld", {}),
    ("reject_tracking", "shopease", {}),
    ("request_refund", "shopease", {"order_number": "ORD-1002", "reason": "Item arrived damaged"}),
    ("dispute_charge", "fitlife", {"transaction_id": "TXN-90545", "reason": "I did not authorise this charge"}),
    ("claim_compensation", "travelquick", {"booking_reference": "TQ7F3K", "flight_number": "TQ 482", "delay_hours": "4.2",
                                           "passenger_name": "Alex Morgan", "contact_email": "alex@example.com"}),
]


def _sim_submissions(site: str) -> list[dict]:
    with db.sim_db() as conn:
        return [dict(r) for r in conn.execute("SELECT * FROM sim_submissions WHERE site=?", (site,)).fetchall()]


@pytest.mark.parametrize("task_type, site, inputs", WORKFLOWS, ids=[f"{t}-{s}" for t, s, _ in WORKFLOWS])
def test_workflow_completes_with_approval(client, task_type, site, inputs):
    data = run_task(client, task_type, site, inputs)
    result = data["result"]
    assert data["session"]["status"] == "completed", data["session"]["status_detail"]
    assert result["success"] == 1 and result["reference"]
    # Exactly one human approval was requested and it was for the final submission.
    assert len(data["approvals"]) == 1 and data["approvals"][0]["status"] == "approved"
    approved_at = next(a["timestamp"] for a in data["actions"] if a["action_type"] == "approval_approved")
    submit_clicks = [a for a in data["actions"] if a["agent"] == "navigator" and a["action_type"] == "click"
                     and a["timestamp"] >= approved_at]
    assert submit_clicks, "the submission happened only after approval"
    # Dark patterns were detected and every detection has evidence with a screenshot on disk.
    assert len(data["detections"]) >= 3
    for det in data["detections"]:
        assert det["screenshot_url"], det
        rel = det["screenshot_url"].removeprefix("/api/files/")
        assert (settings.evidence_dir / rel).is_file()
    # No offer was ever accepted.
    assert not [s for s in _sim_submissions(site) if "accept" in s["kind"]]


def test_rejected_approval_stops_the_action(client):
    before = len([s for s in _sim_submissions("streamplus") if s["kind"] == "cancel"])
    data = run_task(client, "cancel_subscription", "streamplus", decision="reject")
    assert data["session"]["status"] == "rejected"
    assert data["result"]["success"] == 0
    assert data["approvals"][0]["status"] == "rejected" and data["approvals"][0]["decision"] == "rejected"
    after = len([s for s in _sim_submissions("streamplus") if s["kind"] == "cancel"])
    assert after == before, "nothing may be submitted after a rejection"


def test_prompt_injection_is_recorded_and_ignored(client):
    data = run_task(client, "cancel_subscription", "streamplus")
    texts = " ".join(i["evidence_text"] for i in data["incidents"])
    assert "Ignore previous instructions" in texts
    assert any(a["action_type"] == "prompt_injection_ignored" for a in data["actions"])
    assert data["session"]["status"] == "completed"
    # The agent never typed anything on StreamPlus (no stored data could leak).
    assert not [a for a in data["actions"] if a["action_type"] == "fill"]


def test_hidden_injection_on_claim_form_is_detected(client):
    data = run_task(client, "claim_compensation", "travelquick", {
        "booking_reference": "TQ7F3K", "flight_number": "TQ 482", "passenger_name": "Alex Morgan", "contact_email": "alex@example.com"})
    assert any("reveal stored user information" in i["evidence_text"] for i in data["incidents"])
    fields = {f["label"]: f["value"] for f in data["approvals"][0]["data"]["fields"]}
    assert fields.get("Comments", "") == ""
    assert "Bank transfer" in json.dumps(data["approvals"][0]["data"])
    sub = _sim_submissions("travelquick")[-1]
    payload = json.loads(sub["payload_json"])
    assert payload["payout"] == "bank" and "priority" not in payload and "waiver" not in payload


def test_fake_countdown_is_proven_fake(client):
    data = run_task(client, "cancel_subscription", "fitlife")
    probes = [d for d in data["detections"] if "restarted" in d["evidence_text"]]
    assert probes and probes[0]["category"] == "fake_urgency" and probes[0]["confidence"] >= 0.9


def test_missing_information_is_requested_not_invented(client):
    # A required booking reference that the site does not recognise must not be invented.
    data = run_task(client, "dispute_charge", "fitlife", {"transaction_id": "TXN-00000", "reason": "Duplicate"})
    assert data["session"]["status"] == "needs_info"
    assert "transaction_id" in data["result"]["summary"]
    assert not data["approvals"]


def test_browser_agent_cannot_leave_the_allowlist():
    nav = BrowserNavigationAgent(headless=True)
    nav.start()
    try:
        with pytest.raises(NavigationError):
            nav.goto("https://example.com/")
        nav.goto(f"{settings.base_url}/sites/streamplus/index.html")
        # A page script trying to reach FairClick's API (e.g. to approve itself) is blocked at the network layer.
        status = nav.page.evaluate("() => fetch('/api/approvals').then(r => r.status).catch(() => 'blocked')")
        assert status == "blocked"
        assert any("/api/approvals" in u for u in nav.blocked_requests)
    finally:
        nav.close()


def test_evidence_vault_and_export(client):
    records = client.get("/api/evidence").json()
    assert records, "evidence produced by earlier tests"
    rec = records[0]
    for key in ("id", "session_id", "task_id", "site_id", "category", "description", "screenshot_path", "page_url",
                "timestamp", "confidence", "supporting"):
        assert key in rec
    assert client.get(rec["screenshot_url"]).headers["content-type"] == "image/png"
    exported = client.get("/api/evidence/export", params={"format": "json"}).json()
    assert exported["count"] == len(records)
    csv_text = client.get("/api/evidence/export", params={"format": "csv"}).text
    assert csv_text.splitlines()[0].startswith("id,timestamp,site_name")


def test_analytics_match_database(client):
    summary = client.get("/api/analytics/summary").json()
    rows = db.query("SELECT success FROM task_results")
    assert summary["attempted_runs"] == len(rows)
    assert summary["successful_runs"] == sum(r["success"] for r in rows)
    expected_rate = round(100 * sum(r["success"] for r in rows) / len(rows), 1)
    assert summary["success_rate"] == expected_rate
    assert summary["patterns_detected"] == db.query_one("SELECT COUNT(*) AS n FROM detections")["n"]
    assert summary["approvals"]["rejected"] >= 1 and summary["approvals"]["approved"] >= 1


def test_activity_history_is_kept(client):
    sessions = client.get("/api/sessions").json()
    assert len(sessions) >= 10
    detail = client.get(f"/api/sessions/{sessions[0]['id']}").json()
    agents = {a["agent"] for a in detail["actions"]}
    assert {"orchestrator", "navigator", "reasoner", "safety"} <= agents


def test_approval_is_invalidated_if_form_changes(server):
    """If the page alters the form after the user saw it, the approval must not be used."""
    import threading
    import time as _time

    from app.agents.models import Element, Observation
    from app.agents.orchestrator import Orchestrator, broker

    task_id, session_id = db.new_id("tsk_"), db.new_id("ses_")
    db.insert("tasks", {"id": task_id, "user_id": db.DEFAULT_USER_ID, "task_type": "claim_compensation", "site_id": "travelquick",
                        "inputs_json": "{}", "status": "running", "source": "user", "created_at": db.utcnow(), "completed_at": None})
    db.insert("agent_sessions", {"id": session_id, "task_id": task_id, "status": "running", "status_detail": "", "mode": "rule-based",
                                 "current_url": None, "current_step": 0, "live_screenshot": None, "started_at": db.utcnow(), "ended_at": None})
    orch = Orchestrator(session_id, db.query_one("SELECT * FROM tasks WHERE id=?", (task_id,)), {}, threading.Event())
    snapshots = iter([[{"name": "payout", "label": "Payout", "value": "Bank transfer", "hidden": False}],
                      [{"name": "payout", "label": "Payout", "value": "Travel voucher", "hidden": False}]])
    orch.navigator.form_values = lambda form_id: next(snapshots)   # the page switches the payout while we wait
    orch.evidence.step_screenshot = lambda name: None
    submit = Element(fc_id="e1", tag="button", role="button", text="Submit claim", is_submit=True, form_id="f0", form_method="post")
    obs = Observation(url="http://127.0.0.1/sites/travelquick/claim-form.html", path="/sites/travelquick/claim-form.html", title="",
                      step=1, elements=[submit], text_blocks=[], visible_text="", hidden_text="", has_dialog=False)
    result: dict = {}
    worker = threading.Thread(target=lambda: result.setdefault("decision", orch._request_approval(obs, submit)))
    worker.start()
    deadline = _time.time() + 10
    while _time.time() < deadline:
        pending = db.query("SELECT id FROM approval_requests WHERE session_id=? AND status='pending'", (session_id,))
        if pending:
            broker.decide(pending[0]["id"], True, "pytest")
            break
        _time.sleep(0.1)
    worker.join(10)
    assert result["decision"] == "changed"
    assert db.query_one("SELECT COUNT(*) AS n FROM agent_actions WHERE session_id=? AND action_type='approval_invalidated'", (session_id,))["n"] == 1
