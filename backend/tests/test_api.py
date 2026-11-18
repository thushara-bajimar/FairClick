"""API-level functional and input-validation tests (no browser automation)."""
from __future__ import annotations

import pytest


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200 and r.json()["status"] == "ok"
    assert r.json()["mode"] == "rule-based"


def test_meta_lists_tasks_sites_taxonomy(client):
    meta = client.get("/api/meta").json()
    assert {t["id"] for t in meta["task_types"]} == {"cancel_subscription", "reject_tracking", "request_refund",
                                                     "dispute_charge", "claim_compensation"}
    assert len(meta["sites"]) == 5
    assert len(meta["taxonomy"]) == 10


@pytest.mark.parametrize("site", ["streamplus", "shopease", "cookieworld", "fitlife", "travelquick"])
def test_simulated_sites_are_served(client, site):
    r = client.get(f"/sites/{site}/index.html")
    assert r.status_code == 200 and "<html" in r.text.lower()


def test_dashboard_analytics_shape(client):
    s = client.get("/api/analytics/summary").json()
    for key in ("total_tasks", "completed_tasks", "patterns_detected", "approvals", "by_category", "recent_activity"):
        assert key in s


@pytest.mark.parametrize("payload, fragment", [
    ({"task_type": "buy_things", "site_id": "shopease", "inputs": {}}, "task_type"),
    ({"task_type": "request_refund", "site_id": "realbank.com", "inputs": {}}, "site_id"),
    ({"task_type": "request_refund", "site_id": "shopease", "inputs": {"reason": "x"}}, "Missing required input"),
    ({"task_type": "request_refund", "site_id": "shopease", "inputs": {"order_number": "ORD 1; DROP TABLE", "reason": "x"}}, "Invalid format"),
    ({"task_type": "request_refund", "site_id": "shopease", "inputs": {"order_number": "ORD-1", "reason": "x", "password": "hunter2"}}, "Unexpected input"),
    ({"task_type": "dispute_charge", "site_id": "fitlife", "inputs": {"transaction_id": "TXN-1", "reason": "card 4111 1111 1111 1111"}}, "card numbers"),
    ({"task_type": "claim_compensation", "site_id": "travelquick", "inputs": {"booking_reference": "ABC123", "flight_number": "TQ1",
      "passenger_name": "A", "contact_email": "not-an-email"}}, "Invalid format"),
])
def test_task_input_validation(client, payload, fragment):
    r = client.post("/api/tasks", json=payload)
    assert r.status_code == 422
    assert fragment in r.text


def test_task_created_without_start_has_no_session(client):
    r = client.post("/api/tasks", json={"task_type": "reject_tracking", "site_id": "cookieworld", "start": False})
    assert r.status_code == 201 and r.json()["session_id"] is None
    task = client.get(f"/api/tasks/{r.json()['task_id']}").json()
    assert task["status"] == "created" and task["sessions"] == []


def test_unknown_approval_returns_404(client):
    assert client.post("/api/approvals/apr_nope/decision", json={"approved": True}).status_code == 404


def test_evidence_file_path_traversal_blocked(client):
    for path in ("../fairclick.db", "..%2Ffairclick.db", "ses_x/../../fairclick.db"):
        assert client.get(f"/api/files/{path}").status_code == 404


def test_evidence_filters_validated(client):
    assert client.get("/api/evidence", params={"category": "made_up"}).status_code == 400
    assert client.get("/api/evidence", params={"site_id": "nope"}).status_code == 400


def test_settings_roundtrip_and_validation(client):
    r = client.put("/api/settings", json={"step_delay_ms": 500, "display_name": "<b>Sam</b>"})
    assert r.status_code == 200
    prefs = r.json()["preferences"]
    assert prefs["step_delay_ms"] == 500 and prefs["display_name"] == "<b>Sam</b>"  # stored as text; UI renders as text
    assert client.put("/api/settings", json={"step_delay_ms": -5}).status_code == 422
    client.put("/api/settings", json={"step_delay_ms": 0, "display_name": "Demo User"})


def test_settings_never_expose_secrets(client):
    body = client.get("/api/settings").text.lower()
    assert "api_key\"" not in body and "sk-" not in body
    assert "llm_key_configured" in body


def test_sim_form_endpoint_rejects_unknown_forms(client):
    assert client.post("/sites/streamplus/submit/delete_everything", data={}).status_code == 404
