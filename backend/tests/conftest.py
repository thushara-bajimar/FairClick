"""Test fixtures: isolated data directory + the real app served on a free port."""
from __future__ import annotations

import os
import sys
import tempfile
import time
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

_TMP = tempfile.mkdtemp(prefix="fairclick_test_")
os.environ["FAIRCLICK_DATA_DIR"] = _TMP
os.environ["FAIRCLICK_STEP_DELAY_MS"] = "0"
os.environ["FAIRCLICK_HEADLESS"] = "true"
os.environ["FAIRCLICK_APPROVAL_TIMEOUT_S"] = "60"
os.environ["FAIRCLICK_LLM_PROVIDER"] = "none"

from app.devserver import ServerThread, free_port  # noqa: E402

PORT = free_port()
os.environ["FAIRCLICK_PORT"] = str(PORT)

from app import database as db  # noqa: E402
from app.agents import orchestrator  # noqa: E402


@pytest.fixture(scope="session")
def server():
    db.init_db()
    with ServerThread(PORT) as srv:
        yield f"http://127.0.0.1:{PORT}"


@pytest.fixture(scope="session")
def client(server):
    import httpx

    with httpx.Client(base_url=server, timeout=30) as c:
        yield c


def run_task(client, task_type: str, site_id: str, inputs: dict | None = None, decision: str = "approve",
             timeout: float = 180) -> dict:
    """Create a task through the API, answer approval requests, and return the session detail."""
    response = client.post("/api/tasks", json={"task_type": task_type, "site_id": site_id, "inputs": inputs or {}})
    assert response.status_code == 201, response.text
    session_id = response.json()["session_id"]
    deadline = time.time() + timeout
    data = {}
    while time.time() < deadline:
        data = client.get(f"/api/sessions/{session_id}").json()
        for approval in data["approvals"]:
            if approval["status"] == "pending":
                r = client.post(f"/api/approvals/{approval['id']}/decision",
                                json={"approved": decision == "approve", "decided_by": "pytest"})
                assert r.status_code == 200, r.text
        if data["session"]["status"] not in ("starting", "running", "awaiting_approval"):
            break
        time.sleep(0.3)
    orchestrator.wait_for_session(session_id, 20)
    return client.get(f"/api/sessions/{session_id}").json()
