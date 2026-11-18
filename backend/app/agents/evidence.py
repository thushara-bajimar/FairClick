"""Agent 4 - Evidence Collection Agent.

Persists everything that happens in a session: screenshots of detected dark
patterns (with the offending element outlined), page URLs, timestamps, the
visible text that supports each finding, agent actions and security incidents.
All evidence comes from the live browser - nothing is synthesised.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from .. import database as db
from ..config import settings
from .models import Detection, Observation, SecurityIncident
from .navigator import BrowserNavigationAgent


class EvidenceCollectionAgent:
    name = "evidence"

    def __init__(self, session_id: str, task_id: str, site_id: str, navigator: BrowserNavigationAgent,
                 capture_screenshots: bool = True, store_page_text: bool = True) -> None:
        self.session_id = session_id
        self.task_id = task_id
        self.site_id = site_id
        self.navigator = navigator
        self.capture_screenshots = capture_screenshots
        self.store_page_text = store_page_text
        self.session_dir: Path = settings.evidence_dir / session_id
        self.session_dir.mkdir(parents=True, exist_ok=True)
        self._seen: set[tuple[str, str, str]] = set()
        self.detection_count = 0
        self.evidence_count = 0
        self.action_count = 0
        self._last_actions: list[str] = []

    def _relative(self, path: Optional[str]) -> Optional[str]:
        if not path:
            return None
        return Path(path).relative_to(settings.evidence_dir).as_posix()

    # ----------------------------------------------------------------- actions
    def record_action(self, step: int, agent: str, action_type: str, target: str = "", detail: str = "",
                      page_url: str = "", risk: str = "", outcome: str = "") -> None:
        db.insert("agent_actions", {
            "id": db.new_id("act_"), "session_id": self.session_id, "step": step, "agent": agent,
            "action_type": action_type, "target": target[:300], "detail": detail[:1000], "page_url": page_url,
            "risk": risk, "outcome": outcome[:300], "timestamp": db.utcnow(),
        })
        if agent == "navigator" and action_type in {"click", "fill", "check", "uncheck", "select", "reveal", "back"} and outcome.startswith("ok"):
            self.action_count += 1
            self._last_actions = (self._last_actions + [f"{action_type} {target}"])[-5:]

    # -------------------------------------------------------------- detections
    def is_new(self, detection: Detection) -> bool:
        return detection.dedupe_key not in self._seen

    def capture_detection(self, detection: Detection, obs: Observation) -> Optional[str]:
        if not self.is_new(detection):
            return None
        self._seen.add(detection.dedupe_key)
        detection_id = db.new_id("det_")
        timestamp = db.utcnow()
        db.insert("detections", {
            "id": detection_id, "session_id": self.session_id, "task_id": self.task_id, "site_id": self.site_id,
            "category": detection.category, "pattern_name": detection.pattern_name, "description": detection.description,
            "evidence_text": detection.evidence, "location": detection.location, "severity": detection.severity,
            "confidence": detection.confidence, "recommendation": detection.recommendation,
            "page_url": detection.page_url or obs.url, "page_path": detection.page_path or obs.path, "timestamp": timestamp,
        })
        self.detection_count += 1
        screenshot = None
        if self.capture_screenshots:
            shot_path = self.session_dir / f"{detection_id}_{detection.category}.png"
            screenshot = self.navigator.screenshot(shot_path, highlight_id=detection.element_id)
        supporting: dict[str, Any] = {
            "pattern_name": detection.pattern_name,
            "location": detection.location,
            "severity": detection.severity,
            "recommendation": detection.recommendation,
            "page_title": obs.title,
            "observed_step": obs.step,
            "recent_agent_actions": list(self._last_actions),
            "detection_method": "rule-based analysis of DOM text, computed styles and form state",
        }
        if detection.extra:
            supporting["measurements"] = detection.extra
        if self.store_page_text:
            supporting["visible_text_excerpt"] = obs.visible_text[:1500]
        db.insert("evidence_records", {
            "id": db.new_id("evd_"), "session_id": self.session_id, "task_id": self.task_id, "site_id": self.site_id,
            "detection_id": detection_id, "category": detection.category,
            "description": f"{detection.description} Evidence: {detection.evidence}",
            "screenshot_path": self._relative(screenshot), "page_url": obs.url, "timestamp": timestamp,
            "confidence": detection.confidence, "supporting_json": json.dumps(supporting),
        })
        self.evidence_count += 1
        return detection_id

    # --------------------------------------------------------------- incidents
    def record_incident(self, incident: SecurityIncident, obs: Observation) -> bool:
        key = (obs.path, "incident:" + incident.kind, incident.evidence[:60].lower())
        if key in self._seen:
            return False
        self._seen.add(key)
        db.insert("security_incidents", {
            "id": db.new_id("inc_"), "session_id": self.session_id, "kind": incident.kind,
            "description": incident.description, "evidence_text": incident.evidence[:1000], "page_url": obs.url,
            "action_taken": incident.action_taken, "timestamp": db.utcnow(),
        })
        return True

    # ------------------------------------------------------------- screenshots
    def live_screenshot(self, step: int) -> Optional[str]:
        path = self.session_dir / "live.png"
        shot = self.navigator.screenshot(path)
        return self._relative(shot)

    def step_screenshot(self, name: str) -> Optional[str]:
        return self._relative(self.navigator.screenshot(self.session_dir / f"{name}.png"))
