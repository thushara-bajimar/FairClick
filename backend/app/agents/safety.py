"""Agent 5 - Safety and Approval Agent.

Reviews every action the reasoning agent proposes *before* it is executed:

* BLOCKED       - purchases, offers, upsells, off-allowlist destinations, sensitive data entry
* IRREVERSIBLE  - anything that submits a form with POST, or whose wording
                  confirms/submits an outcome -> requires explicit human approval
* REVERSIBLE    - filling/toggling fields (nothing is sent yet)
* SAFE          - navigation and inspection

It also screens page content for prompt injection. Website text can never
grant approval, change the goal or relax these rules.
"""
from __future__ import annotations

import re
from typing import Optional
from urllib.parse import urlparse

from ..security import find_injections, is_allowed_url, is_sensitive_field
from .models import Element, Observation, ProposedAction, Risk, SafetyVerdict, SecurityIncident

FINANCIAL_RE = re.compile(
    r"\b(buy|purchase|pay( now)?|add to (cart|basket)|checkout|place order|upgrade|subscribe|start (my |a |free )?trial|"
    r"renew now|add (priority|insurance|protection)|top up)\b",
    re.IGNORECASE,
)
OFFER_ACCEPT_RE = re.compile(
    r"\b(accept|claim|get|grab|redeem|take|unlock)( the| this| my| your| a)? ?(\d+% off|offer|deal|discount|voucher|free month|bonus|credit)\b|"
    r"\byes,? (give|i want|keep|please|i'?ll take)|\b(keep|stay on|resume) (my )?(membership|subscription|plan|pro|premium)\b|"
    r"\baccept all\b|\ballow all\b",
    re.IGNORECASE,
)
DECLINE_RE = re.compile(r"^\s*(no\b|not now|skip|decline|reject|i don'?t|i do not|continue to|cancel)", re.IGNORECASE)
COMMIT_RE = re.compile(r"\b(submit|confirm|send|finish|finali[sz]e|complete|file|yes,? cancel|cancel (my )?(membership|subscription))\b", re.IGNORECASE)
OFFER_ENDPOINT_RE = re.compile(r"offer|upgrade|purchase|checkout|pay|upsell|retain|accept", re.IGNORECASE)


class SafetyApprovalAgent:
    name = "safety"

    def __init__(self, require_approval_for_consent: bool = True) -> None:
        self.require_approval_for_consent = require_approval_for_consent

    # --------------------------------------------------------- action review
    def review(self, action: ProposedAction, element: Optional[Element], obs: Observation) -> SafetyVerdict:
        if action.kind in ("need_info", "fail", "finish"):
            return SafetyVerdict(Risk.SAFE, True, False, "No browser interaction")
        if action.kind == "back":
            return SafetyVerdict(Risk.SAFE, True, False, "Browser back navigation")
        if element is None:
            return SafetyVerdict(Risk.BLOCKED, False, False, "Target element no longer exists")

        text = element.full_text
        if element.href and not is_allowed_url(element.href):
            return SafetyVerdict(Risk.BLOCKED, False, False, f"Destination {element.href} is outside the approved simulation domains")

        if action.kind == "fill":
            if is_sensitive_field(element.label or element.name):
                return SafetyVerdict(Risk.BLOCKED, False, False, "FairClick never enters passwords, card numbers or similar credentials")
            if not action.field_key:
                return SafetyVerdict(Risk.BLOCKED, False, False, "Only values supplied by the user for this task may be typed")
            return SafetyVerdict(Risk.REVERSIBLE, True, False, "Typing into a form field; nothing is sent until submission")

        if action.kind in ("check", "uncheck", "select"):
            if action.kind == "check" and FINANCIAL_RE.search(text):
                return SafetyVerdict(Risk.BLOCKED, False, False, f"Ticking '{text[:60]}' would add a paid extra")
            if action.kind == "check" and OFFER_ACCEPT_RE.search(text) and not DECLINE_RE.search(text):
                return SafetyVerdict(Risk.BLOCKED, False, False, f"Ticking '{text[:60]}' would accept an offer the user did not ask for")
            return SafetyVerdict(Risk.REVERSIBLE, True, False, "Changing a form field; nothing is sent until submission")

        if action.kind == "reveal":
            return SafetyVerdict(Risk.SAFE, True, False, "Expanding a menu/section to inspect hidden options")

        # Clicks.
        if not DECLINE_RE.search(text):
            if FINANCIAL_RE.search(text):
                return SafetyVerdict(Risk.BLOCKED, False, False, f"'{text[:60]}' looks like a purchase/upgrade - never performed by FairClick")
            if OFFER_ACCEPT_RE.search(text):
                return SafetyVerdict(Risk.BLOCKED, False, False, f"'{text[:60]}' accepts a retention/marketing offer the user did not request")

        if element.is_submit:
            action_path = urlparse(element.form_action).path
            if OFFER_ENDPOINT_RE.search(action_path) and not re.search(r"cancel|refund|claim|dispute|consent", action_path, re.IGNORECASE):
                return SafetyVerdict(Risk.BLOCKED, False, False, f"Form submits to {action_path}, which looks like an offer/purchase endpoint")
            if element.form_method == "post":
                if "consent" in action_path and not self.require_approval_for_consent:
                    return SafetyVerdict(Risk.REVERSIBLE, True, False, "Consent preference change pre-authorised in settings (reversible)")
                return SafetyVerdict(Risk.IRREVERSIBLE, True, True, "This button sends data to the website (POST submission)")
            if COMMIT_RE.search(text) and not re.search(r"\bcontinue\b|\bnext\b", text, re.IGNORECASE):
                return SafetyVerdict(Risk.IRREVERSIBLE, True, True, f"'{text[:60]}' appears to finalise a request")
            return SafetyVerdict(Risk.SAFE, True, False, "Form step that only navigates (GET); nothing is finalised")

        if COMMIT_RE.search(text) and re.search(r"\b(yes|confirm|submit|finish|finali[sz]e)\b", text, re.IGNORECASE) and not element.href:
            return SafetyVerdict(Risk.IRREVERSIBLE, True, True, f"'{text[:60]}' appears to finalise a request")
        return SafetyVerdict(Risk.SAFE, True, False, "Navigation within the simulated site")

    # ------------------------------------------------------ content screening
    def screen_content(self, obs: Observation) -> list[SecurityIncident]:
        incidents: list[SecurityIncident] = []
        for source, text in (("visible", obs.visible_text), ("hidden", obs.hidden_text)):
            for sentence in find_injections(text):
                incidents.append(SecurityIncident(
                    kind="prompt_injection",
                    description=f"Website content ({source} text) contains instructions aimed at an AI agent.",
                    evidence=sentence,
                    action_taken="Ignored. Website content is untrusted data; the user's original goal, the safety rules and the "
                                 "approval requirement are unchanged. No stored user information was disclosed.",
                ))
        return incidents
