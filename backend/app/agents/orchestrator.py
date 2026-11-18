"""Orchestrator - coordinates the five FairClick agents for one task session.

Loop per step:  observe (navigator) -> screen content (safety) -> detect (detector)
-> collect evidence (evidence) -> check completion / decide (reasoner)
-> review (safety) -> [human approval] -> execute (navigator).

Each session runs in its own thread with its own Playwright browser. When an
irreversible action is proposed the thread blocks until a human approves or
rejects it through the API. Nothing on the website can resolve an approval.
"""
from __future__ import annotations

import json
import logging
import re
import threading
import time
from dataclasses import dataclass
from typing import Any, Optional

from .. import database as db
from ..config import settings
from ..security import SITE_IDS, site_start_url
from .detector import DarkPatternDetectionAgent
from .evidence import EvidenceCollectionAgent
from .llm import get_llm_reviewer
from .models import Detection, Observation, ProposedAction, TaskType
from .navigator import BrowserNavigationAgent, NavigationError
from .reasoner import ConsumerRightsReasoningAgent, SessionMemory, signature
from .safety import SafetyApprovalAgent
from .taxonomy import TAXONOMY

log = logging.getLogger("fairclick.orchestrator")

SITE_NAMES = {"streamplus": "StreamPlus", "shopease": "ShopEase", "cookieworld": "CookieWorld",
              "fitlife": "FitLife", "travelquick": "TravelQuick"}
GOAL_PATH_RE = re.compile(r"cancel|refund|return|claim|dispute|consent|privacy", re.IGNORECASE)


# ---------------------------------------------------------------------------
# Approval broker: the only bridge between the waiting agent thread and a human.
# ---------------------------------------------------------------------------
class ApprovalBroker:
    def __init__(self) -> None:
        self._events: dict[str, threading.Event] = {}
        self._lock = threading.Lock()

    def create(self, session_id: str, content: dict[str, Any], page_url: str, screenshot: Optional[str]) -> str:
        request_id = db.new_id("apr_")
        db.insert("approval_requests", {
            "id": request_id, "session_id": session_id, "action_summary": content["action_summary"],
            "reason": content["reason"], "data_json": json.dumps(content["data"]), "consequences": content["consequences"],
            "target_label": content["target_label"], "page_url": page_url, "screenshot_path": screenshot,
            "status": "pending", "created_at": db.utcnow(),
        })
        with self._lock:
            self._events[request_id] = threading.Event()
        return request_id

    def wait(self, request_id: str, timeout_s: float, stop_flag: threading.Event) -> str:
        event = self._events[request_id]
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            if event.wait(0.25):
                break
            if stop_flag.is_set():
                self._expire(request_id, "stopped")
                return "stopped"
        else:
            self._expire(request_id, "expired")
            return "expired"
        row = db.query_one("SELECT status FROM approval_requests WHERE id=?", (request_id,))
        return row["status"] if row else "expired"

    def _expire(self, request_id: str, status: str) -> None:
        db.execute("UPDATE approval_requests SET status=? WHERE id=? AND status='pending'", (status, request_id))

    def decide(self, request_id: str, approved: bool, decided_by: str, comment: str = "") -> dict[str, Any]:
        row = db.query_one("SELECT * FROM approval_requests WHERE id=?", (request_id,))
        if row is None:
            raise KeyError(request_id)
        if row["status"] != "pending":
            raise ValueError(f"Approval request is already {row['status']}")
        decision = "approved" if approved else "rejected"
        db.execute("UPDATE approval_requests SET status=? WHERE id=? AND status='pending'", (decision, request_id))
        db.insert("approval_decisions", {
            "id": db.new_id("dec_"), "request_id": request_id, "decision": decision, "decided_by": decided_by[:60],
            "comment": comment[:500], "decided_at": db.utcnow(),
        })
        with self._lock:
            event = self._events.get(request_id)
        if event:
            event.set()
        return {"request_id": request_id, "decision": decision}


broker = ApprovalBroker()


@dataclass
class SessionHandle:
    session_id: str
    thread: threading.Thread
    stop_flag: threading.Event


_active: dict[str, SessionHandle] = {}
_active_lock = threading.Lock()


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------
class Orchestrator:
    def __init__(self, session_id: str, task: dict[str, Any], options: dict[str, Any], stop_flag: threading.Event) -> None:
        self.session_id = session_id
        self.task = task
        self.task_id = task["id"]
        self.site_id = task["site_id"]
        self.site_name = SITE_NAMES.get(self.site_id, self.site_id)
        self.task_type = TaskType(task["task_type"])
        self.inputs: dict[str, str] = json.loads(task["inputs_json"])
        self.options = options
        self.stop_flag = stop_flag
        self.step = 0
        self.approvals_requested = 0

        self.navigator = BrowserNavigationAgent(headless=options.get("headless", settings.headless),
                                                on_blocked_request=self._on_blocked_request)
        self.reasoner = ConsumerRightsReasoningAgent(self.task_type, self.inputs)
        self.detector = DarkPatternDetectionAgent(goal_scorer=self.reasoner.goal_score)
        self.safety = SafetyApprovalAgent(require_approval_for_consent=options.get("require_approval_for_consent", True))
        self.evidence = EvidenceCollectionAgent(session_id, self.task_id, self.site_id, self.navigator,
                                                capture_screenshots=options.get("capture_screenshots", True),
                                                store_page_text=options.get("store_page_text", True))
        self.llm = get_llm_reviewer()
        self.memory = SessionMemory()

    # ----------------------------------------------------------------- helpers
    def _log(self, agent: str, action_type: str, target: str = "", detail: str = "", risk: str = "", outcome: str = "", url: str = "") -> None:
        self.evidence.record_action(self.step, agent, action_type, target, detail, url, risk, outcome)

    def _set_status(self, status: str, detail: str = "") -> None:
        db.update("agent_sessions", self.session_id, {"status": status, "status_detail": detail[:500]})

    def _on_blocked_request(self, url: str) -> None:
        self._log("safety", "blocked_request", url[:200], "Network request outside the simulation allowlist was blocked", "blocked", "blocked")

    def _record_detection(self, detection: Detection, obs: Observation) -> None:
        if self.evidence.capture_detection(detection, obs):
            self._log("detector", "detected", detection.pattern_name,
                      f"{detection.evidence} | confidence {detection.confidence}", outcome="evidence captured", url=obs.url)

    # -------------------------------------------------------------------- run
    def run(self) -> None:
        started = time.monotonic()
        outcome, summary, reference, completion = "failed", "", None, None
        try:
            self._set_status("running", "Launching browser")
            self.navigator.start()
            start_url = site_start_url(self.site_id)
            self._log("orchestrator", "start", self.site_name,
                      f"Goal: {self.reasoner.profile.objective} Inputs provided: {', '.join(sorted(self.inputs)) or 'none'}", outcome="ok")
            self.navigator.goto(start_url)
            outcome, summary, reference, completion = self._loop()
        except NavigationError as exc:
            outcome, summary = "failed", f"Navigation error: {exc}"
        except Exception as exc:  # noqa: BLE001 - a session must always end cleanly
            log.exception("session %s crashed", self.session_id)
            outcome, summary = "failed", f"Unexpected error: {type(exc).__name__}: {exc}"
        finally:
            self.navigator.close()
            self._finish(outcome, summary, reference, completion, time.monotonic() - started)

    def _loop(self) -> tuple[str, str, Optional[str], Optional[dict[str, Any]]]:
        failures = 0
        probed_paths: set[str] = set()
        last_submit_path = ""
        for _ in range(settings.max_steps):
            if self.stop_flag.is_set():
                return "stopped", "Stopped by the user.", None, None
            obs = self.navigator.observe()
            self.step = obs.step
            if not self.memory.history or self.memory.history[-1] != obs.path:
                self.memory.note_page(obs)
            if GOAL_PATH_RE.search(obs.path):
                self.memory.goal_engaged = True
            live = self.evidence.live_screenshot(self.step)
            db.update("agent_sessions", self.session_id, {"current_url": obs.url, "current_step": self.step, "live_screenshot": live})
            self._log("navigator", "observe", obs.title[:120],
                      f"{len(obs.elements)} interactive elements, {len(obs.forms)} forms, dialog={'yes' if obs.has_dialog else 'no'}",
                      outcome="ok", url=obs.url)

            # Safety: website content is untrusted - screen it for injected instructions.
            for incident in self.safety.screen_content(obs):
                if self.evidence.record_incident(incident, obs):
                    self._log("safety", "prompt_injection_ignored", "website content", f"\"{incident.evidence}\" -> {incident.action_taken}",
                              risk="blocked", outcome="ignored", url=obs.url)

            # Detection + evidence.
            detections = self.detector.analyze(obs)
            if self.llm:
                detections += self.llm.review(obs)
            for det in detections:
                self._record_detection(det, obs)
            if obs.timers and obs.path not in probed_paths and obs.path != last_submit_path and any(
                    d.category == "fake_urgency" for d in detections):
                probed_paths.add(obs.path)
                for timer in obs.timers[:2]:
                    probe = self.navigator.probe_timer(timer["id"])
                    self._log("navigator", "probe_timer", timer["text"][:80], json.dumps(probe), outcome="ok", url=obs.url)
                    det = self.detector.timer_probe_detection(obs, timer, probe or {})
                    if det:
                        self._record_detection(det, obs)
                continue  # page was reloaded by the probe - observe again

            completion = self.reasoner.check_completion(obs, self.memory)
            if completion:
                self._session_level_detections(obs)
                ref = completion.get("reference")
                note = " ".join(completion.get("notes", []))
                if not completion.get("verified", True):
                    return "partial", f"Submitted, but verification found issues. {note}", ref, completion
                return "completed", f"{self.reasoner.profile.title} completed on {self.site_name}." + (f" Reference {ref}." if ref else "") + (f" {note}" if note else ""), ref, completion

            action = self.reasoner.decide(obs, self.memory)
            element = obs.element(action.element_id) if action.element_id else None
            self._log("reasoner", "decide", element.descriptor if element else action.kind, action.rationale, outcome=action.kind, url=obs.url)

            if action.kind == "need_info":
                return "needs_info", "More information is needed from you: " + ", ".join(action.missing), None, None
            if action.kind == "fail":
                return "failed", action.rationale, None, None

            verdict = self.safety.review(action, element, obs)
            self._log("safety", "review", element.descriptor if element else action.kind, verdict.reason, risk=verdict.risk.value,
                      outcome="allowed" if verdict.allowed else "blocked", url=obs.url)
            if not verdict.allowed:
                if element:
                    self.memory.blocked.add(signature(element))
                continue

            if verdict.requires_approval and element is not None:
                decision = self._request_approval(obs, element)
                if decision != "approved":
                    reason = {"rejected": "You rejected the final action, so nothing was submitted.",
                          "changed": "The website changed the form after you approved it, so nothing was submitted.",
                              "expired": "The approval request expired, so nothing was submitted.",
                              "stopped": "Stopped by the user before approval; nothing was submitted."}.get(decision, decision)
                    return ("rejected" if decision == "rejected" else "stopped"), reason, None, None

            try:
                result = self.navigator.execute(action, element)
            except NavigationError as exc:
                failures += 1
                self._log("navigator", action.kind, element.descriptor if element else "", str(exc), verdict.risk.value, "error", obs.url)
                if element:
                    self.memory.clicks[(obs.path, signature(element))] += 1
                if failures >= 5:
                    return "failed", f"Too many failed interactions; last error: {exc}", None, None
                continue
            self._log("navigator", action.kind, element.descriptor if element else action.kind,
                      action.rationale if action.kind != "fill" else f"Typed the user's {action.field_key.replace('_', ' ')}",
                      verdict.risk.value, f"ok: {result}", obs.url)

            if element is not None:
                if action.kind in ("check", "uncheck", "select", "fill"):
                    self.detector.note_modified(obs, element)
                if action.kind == "click":
                    self.memory.clicks[(obs.path, signature(element))] += 1
                elif action.kind == "reveal":
                    self.memory.revealed.add(signature(element))
                if action.kind == "click" and (self.reasoner.goal_score(element) >= 5 or action.goal_step == "decline_offer"):
                    self.memory.goal_engaged = True
                if action.kind == "click" and element.is_submit and element.form_method == "post" and action.goal_step == "submit":
                    self.memory.submitted = True
                    last_submit_path = obs.path
            delay = self.options.get("step_delay_ms", settings.step_delay_ms)
            if delay:
                time.sleep(delay / 1000)
        return "failed", f"Step limit ({settings.max_steps}) reached before the goal was completed.", None, None

    def _session_level_detections(self, obs: Observation) -> None:
        journey = list(dict.fromkeys(self.memory.history))
        if len(journey) >= 5:
            det = Detection(
                category="obstruction", pattern_name=TAXONOMY["obstruction"]["name"],
                description="Completing the request required an unusually long sequence of screens.",
                evidence=f"{len(journey)} distinct pages were needed: {' -> '.join(journey)}",
                location="whole journey", severity="medium", confidence=0.7,
                recommendation=TAXONOMY["obstruction"]["recommendation"], page_url=obs.url, page_path="session",
                extra={"pages": journey, "retention_screens": self.detector.retention_pages})
            self._record_detection(det, obs)

    def _request_approval(self, obs: Observation, element) -> str:
        form_values = self.navigator.form_values(element.form_id) if element.form_id else []
        content = self.reasoner.approval_content(obs, element, form_values, self.site_name)
        screenshot = self.evidence.step_screenshot(f"approval_step{self.step}")
        request_id = broker.create(self.session_id, content, obs.url, screenshot)
        self.approvals_requested += 1
        self._log("safety", "approval_requested", content["target_label"], content["action_summary"], "irreversible", "pending", obs.url)
        self._set_status("awaiting_approval", content["action_summary"])
        decision = broker.wait(request_id, self.options.get("approval_timeout_s", settings.approval_timeout_s), self.stop_flag)
        self._log("human", f"approval_{decision}", content["target_label"], f"Approval request {request_id}: {decision}",
                  "irreversible", decision, obs.url)
        self._set_status("running", f"Approval {decision}")
        if decision == "approved" and element.form_id:
            # Bind the approval to what the user saw: if the page changed the form
            # while we waited, the approval no longer applies.
            current = self.navigator.form_values(element.form_id)
            if current != form_values:
                self._log("safety", "approval_invalidated", content["target_label"],
                          "Form contents changed after approval was requested; nothing was submitted.", "irreversible", "blocked", obs.url)
                return "changed"
        return decision

    def _finish(self, outcome: str, summary: str, reference: Optional[str], completion: Optional[dict[str, Any]], duration: float) -> None:
        success = outcome == "completed"
        document = self.reasoner.prepared_document(self.site_name, reference, self.memory) if success else None
        now = db.utcnow()
        session_status = {"completed": "completed", "partial": "completed", "rejected": "rejected", "needs_info": "needs_info",
                          "stopped": "stopped"}.get(outcome, "failed")
        db.update("agent_sessions", self.session_id, {"status": session_status, "status_detail": summary[:500], "ended_at": now})
        db.update("tasks", self.task_id, {"status": session_status, "completed_at": now})
        db.insert("task_results", {
            "id": db.new_id("res_"), "task_id": self.task_id, "session_id": self.session_id, "outcome": outcome,
            "success": 1 if success else 0, "summary": summary[:1000], "reference": reference, "prepared_document": document,
            "interactions": self.evidence.action_count, "pages_visited": len(set(self.memory.history)),
            "duration_seconds": round(duration, 2), "patterns_detected": self.evidence.detection_count,
            "evidence_count": self.evidence.evidence_count, "approvals_requested": self.approvals_requested, "created_at": now,
        })
        self._log("orchestrator", "finish", outcome, summary, outcome=outcome)


# ---------------------------------------------------------------------------
# Session management API used by the routers / benchmark
# ---------------------------------------------------------------------------
def start_session(task_id: str, options: Optional[dict[str, Any]] = None) -> str:
    task = db.query_one("SELECT * FROM tasks WHERE id=?", (task_id,))
    if task is None:
        raise KeyError(task_id)
    if task["site_id"] not in SITE_IDS:
        raise ValueError("Unknown site")
    session_id = db.new_id("ses_")
    db.insert("agent_sessions", {
        "id": session_id, "task_id": task_id, "status": "starting", "status_detail": "Queued",
        "mode": "rule-based" if get_llm_reviewer() is None else "rule-based + LLM review",
        "current_url": None, "current_step": 0, "live_screenshot": None, "started_at": db.utcnow(), "ended_at": None,
    })
    db.update("tasks", task_id, {"status": "running"})
    stop_flag = threading.Event()
    orchestrator = Orchestrator(session_id, task, options or {}, stop_flag)
    thread = threading.Thread(target=orchestrator.run, name=f"session-{session_id}", daemon=True)
    with _active_lock:
        _active[session_id] = SessionHandle(session_id, thread, stop_flag)
    thread.start()
    return session_id


def stop_session(session_id: str) -> bool:
    with _active_lock:
        handle = _active.get(session_id)
    if handle is None or not handle.thread.is_alive():
        return False
    handle.stop_flag.set()
    return True


def wait_for_session(session_id: str, timeout: float = 120) -> None:
    with _active_lock:
        handle = _active.get(session_id)
    if handle:
        handle.thread.join(timeout)
