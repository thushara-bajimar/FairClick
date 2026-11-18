"""Structured messages exchanged between FairClick agents.

Every agent communicates through these typed structures rather than free text,
which keeps the pipeline auditable and makes an LLM-backed agent a drop-in
replacement for a rule-based one.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Optional


class TaskType(str, Enum):
    CANCEL_SUBSCRIPTION = "cancel_subscription"
    REJECT_TRACKING = "reject_tracking"
    REQUEST_REFUND = "request_refund"
    DISPUTE_CHARGE = "dispute_charge"
    CLAIM_COMPENSATION = "claim_compensation"


class Risk(str, Enum):
    SAFE = "safe"                  # read-only / navigation
    REVERSIBLE = "reversible"      # form edits, toggles - nothing sent yet
    IRREVERSIBLE = "irreversible"  # submits data / confirms an outcome -> approval
    BLOCKED = "blocked"            # never allowed (purchases, offers, off-domain)


@dataclass
class Element:
    """An interactive element observed on the page."""
    fc_id: str                     # id injected by the navigator (data-fc-id)
    tag: str
    role: str                      # button | link | checkbox | radio | textbox | select | summary
    text: str                      # visible text / accessible name
    href: str = ""
    input_type: str = ""
    name: str = ""
    label: str = ""                # associated <label> / aria-label text
    value: str = ""
    checked: Optional[bool] = None
    required: bool = False
    disabled: bool = False
    visible: bool = True
    in_viewport: bool = True
    inside_closed_details: bool = False
    inside_dialog: bool = False
    form_id: str = ""              # data-fc-form id of the enclosing form
    form_method: str = ""
    form_action: str = ""
    is_submit: bool = False
    options: list[dict[str, Any]] = field(default_factory=list)  # for <select>
    font_size: float = 0.0
    font_weight: int = 400
    color: str = ""
    background: str = ""
    contrast: float = 21.0
    opacity: float = 1.0
    area: float = 0.0
    x: float = 0.0
    y: float = 0.0
    region: str = "main"           # header | nav | main | footer | dialog | banner

    @property
    def descriptor(self) -> str:
        """Human-readable description used in logs and evidence."""
        name = (self.text or self.label or self.name or self.fc_id).strip()
        return f"{self.role} '{name[:80]}'"

    @property
    def full_text(self) -> str:
        return " ".join(t for t in (self.text, self.label) if t).strip()


@dataclass
class TextBlock:
    text: str
    tag: str
    font_size: float
    contrast: float
    visible: bool
    region: str
    fc_id: str = ""


@dataclass
class Observation:
    """Snapshot of a page produced by the Browser Navigation Agent."""
    url: str
    path: str
    title: str
    step: int
    elements: list[Element]
    text_blocks: list[TextBlock]
    visible_text: str
    hidden_text: str               # text present in the DOM but not visible
    has_dialog: bool
    forms: list[dict[str, Any]] = field(default_factory=list)
    timers: list[dict[str, Any]] = field(default_factory=list)

    def element(self, fc_id: str) -> Optional[Element]:
        return next((e for e in self.elements if e.fc_id == fc_id), None)


@dataclass
class Detection:
    category: str
    pattern_name: str
    description: str
    evidence: str
    location: str
    severity: str
    confidence: float
    recommendation: str
    element_id: str = ""           # element to highlight in the screenshot
    page_url: str = ""
    page_path: str = ""
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def dedupe_key(self) -> tuple[str, str, str]:
        return (self.page_path, self.category, self.evidence[:60].lower())

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ProposedAction:
    kind: str                      # click | fill | check | uncheck | select | reveal | back | finish | need_info | fail
    element_id: str = ""
    value: str = ""
    rationale: str = ""
    score: float = 0.0
    goal_step: str = ""            # navigate | decline_offer | prepare_form | submit | reveal
    field_key: str = ""            # which user input is being used (for fills)
    missing: list[str] = field(default_factory=list)


@dataclass
class SafetyVerdict:
    risk: Risk
    allowed: bool
    requires_approval: bool
    reason: str


@dataclass
class SecurityIncident:
    kind: str
    description: str
    evidence: str
    action_taken: str
