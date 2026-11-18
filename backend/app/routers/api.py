"""FairClick REST API (mounted at /api)."""
from __future__ import annotations

import csv
import io
import json
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse, Response

from .. import database as db
from ..agents import orchestrator
from ..agents.goals import PROFILES, RECOMMENDED_SITES, TASK_INPUT_FIELDS
from ..agents.llm import get_llm_reviewer
from ..agents.models import TaskType
from ..agents.orchestrator import SITE_NAMES
from ..agents.taxonomy import TAXONOMY
from ..config import BACKEND_DIR, settings
from ..schemas import ApprovalDecision, SettingsUpdate, TaskCreate
from ..security import SITE_IDS

router = APIRouter(prefix="/api")

SITE_INFO = {
    "streamplus": {"name": "StreamPlus", "kind": "Video streaming", "patterns": ["Hidden cancellation", "Retention offers", "Confirm-shaming", "Repeated confirmations", "Prompt injection"]},
    "shopease": {"name": "ShopEase", "kind": "Online store", "patterns": ["Confusing refund navigation", "Unnecessary steps", "Misleading refund options"]},
    "cookieworld": {"name": "CookieWorld", "kind": "News magazine", "patterns": ["Pre-selected tracking", "Prominent accept-all", "Hidden reject-all", "Confusing consent language"]},
    "fitlife": {"name": "FitLife", "kind": "Fitness app", "patterns": ["Forced continuity", "Fake countdown", "Misleading offers", "Repeated prompts"]},
    "travelquick": {"name": "TravelQuick", "kind": "Travel booking", "patterns": ["Complicated claim form", "Unnecessary steps", "Misleading urgency", "Hidden claim option"]},
}


def _user_settings() -> dict[str, Any]:
    rows = db.query("SELECT key, value FROM user_settings WHERE user_id=?", (db.DEFAULT_USER_ID,))
    return {r["key"]: json.loads(r["value"]) for r in rows}


def _session_options() -> dict[str, Any]:
    prefs = _user_settings()
    return {
        "headless": prefs.get("headless_browser", settings.headless) and settings.headless,
        "step_delay_ms": prefs.get("step_delay_ms", settings.step_delay_ms),
        "capture_screenshots": prefs.get("capture_screenshots", True),
        "store_page_text": prefs.get("store_page_text", True),
        "require_approval_for_consent": prefs.get("require_approval_for_consent", True),
    }


def _evidence_url(rel: Optional[str]) -> Optional[str]:
    return f"/api/files/{rel}" if rel else None


# ----------------------------------------------------------------------- meta
@router.get("/health")
def health() -> dict[str, Any]:
    return {"status": "ok", "mode": "rule-based" if get_llm_reviewer() is None else "rule-based + LLM review"}


@router.get("/meta")
def meta() -> dict[str, Any]:
    return {
        "task_types": [
            {"id": t.value, "title": PROFILES[t].title, "objective": PROFILES[t].objective,
             "fields": TASK_INPUT_FIELDS[t.value], "recommended_sites": RECOMMENDED_SITES[t.value]}
            for t in TaskType
        ],
        "sites": [{"id": s, **SITE_INFO[s], "url": f"/sites/{s}/index.html"} for s in SITE_IDS],
        "taxonomy": [{"id": k, **v} for k, v in TAXONOMY.items()],
        "agent_mode": "rule-based" if get_llm_reviewer() is None else "rule-based + LLM review",
    }


# ---------------------------------------------------------------------- tasks
@router.post("/tasks", status_code=201)
def create_task(body: TaskCreate) -> dict[str, Any]:
    task_id = db.new_id("tsk_")
    db.insert("tasks", {
        "id": task_id, "user_id": db.DEFAULT_USER_ID, "task_type": body.task_type, "site_id": body.site_id,
        "inputs_json": json.dumps(body.inputs), "status": "created", "source": "user",
        "created_at": db.utcnow(), "completed_at": None,
    })
    session_id = orchestrator.start_session(task_id, _session_options()) if body.start else None
    return {"task_id": task_id, "session_id": session_id}


@router.post("/tasks/{task_id}/run", status_code=201)
def rerun_task(task_id: str) -> dict[str, Any]:
    if not db.query_one("SELECT id FROM tasks WHERE id=?", (task_id,)):
        raise HTTPException(404, "Task not found")
    return {"task_id": task_id, "session_id": orchestrator.start_session(task_id, _session_options())}


def _task_row(row: dict[str, Any]) -> dict[str, Any]:
    row = dict(row)
    row["inputs"] = json.loads(row.pop("inputs_json"))
    row["site_name"] = SITE_NAMES.get(row["site_id"], row["site_id"])
    row["task_title"] = PROFILES[TaskType(row["task_type"])].title
    return row


@router.get("/tasks")
def list_tasks(limit: int = Query(50, ge=1, le=500)) -> list[dict[str, Any]]:
    rows = db.query(
        "SELECT t.*, (SELECT id FROM agent_sessions s WHERE s.task_id=t.id ORDER BY started_at DESC LIMIT 1) AS latest_session_id, "
        "(SELECT COUNT(*) FROM detections d WHERE d.task_id=t.id) AS detection_count "
        "FROM tasks t ORDER BY created_at DESC LIMIT ?", (limit,))
    return [_task_row(r) for r in rows]


@router.get("/tasks/{task_id}")
def get_task(task_id: str) -> dict[str, Any]:
    row = db.query_one("SELECT * FROM tasks WHERE id=?", (task_id,))
    if not row:
        raise HTTPException(404, "Task not found")
    task = _task_row(row)
    task["sessions"] = db.query("SELECT * FROM agent_sessions WHERE task_id=? ORDER BY started_at DESC", (task_id,))
    task["results"] = db.query("SELECT * FROM task_results WHERE task_id=? ORDER BY created_at DESC", (task_id,))
    return task


# ------------------------------------------------------------------- sessions
@router.get("/sessions")
def list_sessions(limit: int = Query(50, ge=1, le=500)) -> list[dict[str, Any]]:
    return db.query(
        "SELECT s.*, t.task_type, t.site_id FROM agent_sessions s JOIN tasks t ON t.id=s.task_id ORDER BY s.started_at DESC LIMIT ?",
        (limit,))


@router.get("/sessions/{session_id}")
def get_session(session_id: str) -> dict[str, Any]:
    session = db.query_one("SELECT * FROM agent_sessions WHERE id=?", (session_id,))
    if not session:
        raise HTTPException(404, "Session not found")
    task = _task_row(db.query_one("SELECT * FROM tasks WHERE id=?", (session["task_id"],)))
    session["live_screenshot_url"] = _evidence_url(session.get("live_screenshot"))
    approvals = db.query(
        "SELECT r.*, d.decision, d.decided_by, d.comment, d.decided_at FROM approval_requests r "
        "LEFT JOIN approval_decisions d ON d.request_id=r.id WHERE r.session_id=? ORDER BY r.created_at", (session_id,))
    for a in approvals:
        a["data"] = json.loads(a.pop("data_json"))
        a["screenshot_url"] = _evidence_url(a.get("screenshot_path"))
    detections = db.query("SELECT * FROM detections WHERE session_id=? ORDER BY timestamp", (session_id,))
    evidence = db.query("SELECT id, detection_id, screenshot_path FROM evidence_records WHERE session_id=?", (session_id,))
    shots = {e["detection_id"]: _evidence_url(e["screenshot_path"]) for e in evidence}
    for d in detections:
        d["screenshot_url"] = shots.get(d["id"])
    return {
        "session": session,
        "task": task,
        "actions": db.query("SELECT * FROM agent_actions WHERE session_id=? ORDER BY timestamp, rowid", (session_id,)),
        "detections": detections,
        "approvals": approvals,
        "incidents": db.query("SELECT * FROM security_incidents WHERE session_id=? ORDER BY timestamp", (session_id,)),
        "result": db.query_one("SELECT * FROM task_results WHERE session_id=?", (session_id,)),
    }


@router.post("/sessions/{session_id}/stop")
def stop_session(session_id: str) -> dict[str, Any]:
    if not db.query_one("SELECT id FROM agent_sessions WHERE id=?", (session_id,)):
        raise HTTPException(404, "Session not found")
    return {"stopping": orchestrator.stop_session(session_id)}


# ------------------------------------------------------------------ approvals
@router.get("/approvals")
def list_approvals(status: Optional[str] = Query(None, pattern="^(pending|approved|rejected|expired|stopped)$")) -> list[dict[str, Any]]:
    sql = ("SELECT r.*, t.task_type, t.site_id, d.decision, d.decided_at FROM approval_requests r "
           "JOIN agent_sessions s ON s.id=r.session_id JOIN tasks t ON t.id=s.task_id "
           "LEFT JOIN approval_decisions d ON d.request_id=r.id")
    params: tuple = ()
    if status:
        sql += " WHERE r.status=?"
        params = (status,)
    rows = db.query(sql + " ORDER BY r.created_at DESC", params)
    for r in rows:
        r["data"] = json.loads(r.pop("data_json"))
        r["screenshot_url"] = _evidence_url(r.get("screenshot_path"))
    return rows


@router.post("/approvals/{request_id}/decision")
def decide_approval(request_id: str, body: ApprovalDecision) -> dict[str, Any]:
    try:
        return orchestrator.broker.decide(request_id, body.approved, body.decided_by or "user", body.comment)
    except KeyError:
        raise HTTPException(404, "Approval request not found")
    except ValueError as exc:
        raise HTTPException(409, str(exc))


# ------------------------------------------------------------------- evidence
def _evidence_rows(category: Optional[str], site_id: Optional[str], task_id: Optional[str]) -> list[dict[str, Any]]:
    sql = ("SELECT e.*, d.pattern_name, d.severity, d.location, d.evidence_text, d.recommendation, t.task_type "
           "FROM evidence_records e LEFT JOIN detections d ON d.id=e.detection_id JOIN tasks t ON t.id=e.task_id WHERE 1=1")
    params: list[Any] = []
    for column, value in (("e.category", category), ("e.site_id", site_id), ("e.task_id", task_id)):
        if value:
            sql += f" AND {column}=?"
            params.append(value)
    rows = db.query(sql + " ORDER BY e.timestamp DESC", params)
    for r in rows:
        r["supporting"] = json.loads(r.pop("supporting_json"))
        r["screenshot_url"] = _evidence_url(r.get("screenshot_path"))
        r["site_name"] = SITE_NAMES.get(r["site_id"], r["site_id"])
    return rows


@router.get("/evidence")
def list_evidence(category: Optional[str] = None, site_id: Optional[str] = None, task_id: Optional[str] = None) -> list[dict[str, Any]]:
    if category and category not in TAXONOMY:
        raise HTTPException(400, "Unknown category")
    if site_id and site_id not in SITE_IDS:
        raise HTTPException(400, "Unknown site")
    return _evidence_rows(category, site_id, task_id)


@router.get("/evidence/export")
def export_evidence(format: str = Query("json", pattern="^(json|csv)$"), task_id: Optional[str] = None) -> Response:
    rows = _evidence_rows(None, None, task_id)
    if format == "json":
        payload = json.dumps({"exported_at": db.utcnow(), "count": len(rows), "records": rows}, indent=2)
        return Response(payload, media_type="application/json",
                        headers={"Content-Disposition": 'attachment; filename="fairclick_evidence.json"'})
    buffer = io.StringIO()
    columns = ["id", "timestamp", "site_name", "task_type", "category", "pattern_name", "severity", "confidence",
               "page_url", "location", "evidence_text", "screenshot_path", "session_id", "task_id"]
    writer = csv.DictWriter(buffer, fieldnames=columns, extrasaction="ignore")
    writer.writeheader()
    for r in rows:
        writer.writerow({c: r.get(c, "") for c in columns})
    return Response(buffer.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition": 'attachment; filename="fairclick_evidence.csv"'})


@router.get("/files/{file_path:path}")
def evidence_file(file_path: str) -> FileResponse:
    base = settings.evidence_dir.resolve()
    target = (base / file_path).resolve()
    if base not in target.parents or not target.is_file() or target.suffix.lower() != ".png":
        raise HTTPException(404, "File not found")
    return FileResponse(target, media_type="image/png", headers={"Cache-Control": "no-store"})


# ------------------------------------------------------------------ analytics
@router.get("/analytics/summary")
def analytics_summary() -> dict[str, Any]:
    tasks = db.query_one(
        "SELECT COUNT(*) AS total, SUM(status='completed') AS completed, SUM(status='failed') AS failed, "
        "SUM(status='rejected') AS rejected, SUM(status IN ('running','created')) AS running FROM tasks")
    sessions_with_result = db.query_one("SELECT COUNT(*) AS n, SUM(success) AS ok, AVG(CASE WHEN success=1 THEN duration_seconds END) AS avg_duration, "
                                        "SUM(interactions) AS interactions, AVG(CASE WHEN success=1 THEN interactions END) AS avg_interactions "
                                        "FROM task_results")
    attempted = sessions_with_result["n"] or 0
    succeeded = sessions_with_result["ok"] or 0
    by_category = db.query("SELECT category, COUNT(*) AS count FROM detections GROUP BY category ORDER BY count DESC")
    by_site = db.query("SELECT site_id, COUNT(*) AS count FROM detections GROUP BY site_id")
    by_task = db.query(
        "SELECT t.task_type, COUNT(r.id) AS attempted, SUM(r.success) AS succeeded, AVG(r.duration_seconds) AS avg_duration "
        "FROM task_results r JOIN tasks t ON t.id=r.task_id GROUP BY t.task_type")
    approvals = db.query_one(
        "SELECT COUNT(*) AS total, SUM(status='pending') AS pending, SUM(status='approved') AS approved, "
        "SUM(status='rejected') AS rejected FROM approval_requests")
    recent = db.query(
        "SELECT a.timestamp, a.agent, a.action_type, a.target, a.outcome, a.session_id, t.task_type, t.site_id "
        "FROM agent_actions a JOIN agent_sessions s ON s.id=a.session_id JOIN tasks t ON t.id=s.task_id "
        "WHERE a.action_type IN ('start','finish','detected','approval_requested','approval_approved','approval_rejected','prompt_injection_ignored') "
        "ORDER BY a.timestamp DESC LIMIT 15")
    per_day = db.query("SELECT substr(created_at,1,10) AS day, COUNT(*) AS tasks, SUM(success) AS succeeded FROM task_results GROUP BY day ORDER BY day")
    incidents = db.query_one("SELECT COUNT(*) AS n FROM security_incidents")
    return {
        "total_tasks": tasks["total"] or 0,
        "completed_tasks": tasks["completed"] or 0,
        "failed_tasks": tasks["failed"] or 0,
        "rejected_tasks": tasks["rejected"] or 0,
        "running_tasks": tasks["running"] or 0,
        "attempted_runs": attempted,
        "successful_runs": succeeded,
        "success_rate": round(100 * succeeded / attempted, 1) if attempted else None,
        "patterns_detected": sum(r["count"] for r in by_category),
        "evidence_records": db.query_one("SELECT COUNT(*) AS n FROM evidence_records")["n"],
        "average_completion_seconds": round(sessions_with_result["avg_duration"], 2) if sessions_with_result["avg_duration"] else None,
        "total_interactions": sessions_with_result["interactions"] or 0,
        "average_interactions": round(sessions_with_result["avg_interactions"], 1) if sessions_with_result["avg_interactions"] else None,
        "approvals": {k: (approvals[k] or 0) for k in ("total", "pending", "approved", "rejected")},
        "security_incidents": incidents["n"],
        "by_category": [{"category": r["category"], "name": TAXONOMY[r["category"]]["name"], "count": r["count"]} for r in by_category],
        "by_site": [{"site_id": r["site_id"], "name": SITE_NAMES.get(r["site_id"], r["site_id"]), "count": r["count"]} for r in by_site],
        "by_task": [{**r, "title": PROFILES[TaskType(r["task_type"])].title} for r in by_task],
        "per_day": per_day,
        "recent_activity": recent,
    }


@router.get("/analytics/benchmark")
def latest_benchmark() -> dict[str, Any]:
    path = BACKEND_DIR / "benchmark" / "results" / "latest.json"
    if not path.exists():
        return {"available": False}
    return {"available": True, **json.loads(path.read_text(encoding="utf-8"))}


# ------------------------------------------------------------------- settings
@router.get("/settings")
def get_settings() -> dict[str, Any]:
    return {"preferences": _user_settings(), "server": {
        "agent_mode": "rule-based" if get_llm_reviewer() is None else "rule-based + LLM review",
        "llm_provider": settings.llm_provider, "llm_key_configured": bool(settings.anthropic_api_key),
        "max_steps": settings.max_steps, "approval_timeout_s": settings.approval_timeout_s,
        "allowed_navigation": f"{settings.base_url}/sites/* only",
    }}


@router.put("/settings")
def update_settings(body: SettingsUpdate) -> dict[str, Any]:
    for key, value in body.changes().items():
        db.execute("INSERT OR REPLACE INTO user_settings(user_id, key, value) VALUES (?,?,?)",
                   (db.DEFAULT_USER_ID, key, json.dumps(value)))
        if key == "display_name":
            db.execute("UPDATE users SET display_name=? WHERE id=?", (value, db.DEFAULT_USER_ID))
    return get_settings()


@router.delete("/history")
def clear_history(include_benchmark: bool = False) -> dict[str, Any]:
    """Delete finished task history (and its evidence files). Running sessions are kept."""
    where = "t.status NOT IN ('running','created')" + ("" if include_benchmark else " AND t.source='user'")
    sessions = db.query(f"SELECT s.id FROM agent_sessions s JOIN tasks t ON t.id=s.task_id WHERE {where}")
    for s in sessions:
        folder = settings.evidence_dir / s["id"]
        if folder.is_dir():
            for f in folder.iterdir():
                f.unlink(missing_ok=True)
            folder.rmdir()
    count = db.query_one(f"SELECT COUNT(*) AS n FROM tasks t WHERE {where}")["n"]
    db.execute(f"DELETE FROM tasks WHERE id IN (SELECT t.id FROM tasks t WHERE {where})")
    return {"deleted_tasks": count, "deleted_sessions": len(sessions)}
