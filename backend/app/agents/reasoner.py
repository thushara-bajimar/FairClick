"""Agent 3 - Consumer Rights Reasoning Agent.

Decides the next step towards the user's goal from a structured observation.
It scores every interactive element against the goal profile (goal / stage /
decline vocabulary minus offer & upsell vocabulary), prepares forms using only
the information the user supplied, and decides when the task is complete.

The user's goal is fixed when the task is created. Nothing on the website can
change it: page text is only ever *scored*, never interpreted as instructions.
"""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Mapping, Optional
from urllib.parse import urlparse

from ..security import is_allowed_url, is_sensitive_field
from .goals import NEUTRAL_CHOICE, PROFILES, GoalProfile
from .models import Element, Observation, ProposedAction, TaskType

REFERENCE_RE = re.compile(r"\b([A-Z]{2,4}-[A-Z0-9]{4,10})\b")
ESSENTIAL_RE = re.compile(r"strictly necessary|essential|required for the site", re.IGNORECASE)
CLICKABLE_ROLES = {"link", "button", "summary", "menuitem"}
FIELD_ROLES = {"textbox", "select", "checkbox", "radio", "switch"}
MIN_SCORE = 2.0


def signature(el: Element) -> str:
    href = urlparse(el.href).path if el.href else ""
    return f"{el.role}|{(el.full_text or el.name)[:60].lower()}|{href}|{el.name}"


@dataclass
class SessionMemory:
    clicks: Counter = field(default_factory=Counter)          # (path, signature) -> count
    page_visits: Counter = field(default_factory=Counter)     # path -> count
    field_attempts: Counter = field(default_factory=Counter)  # (path, field signature) -> count
    history: list[str] = field(default_factory=list)
    backtracks: int = 0
    goal_engaged: bool = False
    submitted: bool = False
    submitted_path: str = ""
    retention_pages: set = field(default_factory=set)
    observed_facts: list[str] = field(default_factory=list)
    blocked: set = field(default_factory=set)                 # signatures the safety agent blocked
    revealed: set = field(default_factory=set)

    def note_page(self, obs: Observation) -> None:
        self.page_visits[obs.path] += 1
        self.history.append(obs.path)


class ConsumerRightsReasoningAgent:
    name = "reasoner"

    def __init__(self, task_type: TaskType, inputs: Mapping[str, str]) -> None:
        self.task_type = task_type
        self.profile: GoalProfile = PROFILES[task_type]
        # Freeze the user's request: the agent works from this copy only.
        self.inputs: Mapping[str, str] = MappingProxyType({k: str(v) for k, v in inputs.items() if str(v).strip()})
        self._rx = self.profile.compiled()
        self._uncheck = re.compile(self.profile.uncheck_pattern, re.IGNORECASE)
        self._check = re.compile(self.profile.check_pattern, re.IGNORECASE)
        self._success = [re.compile(p, re.IGNORECASE) for p in self.profile.success_patterns]

    # ------------------------------------------------------------------ scoring
    def _group_score(self, group: str, text: str) -> float:
        best = 0.0
        for pattern, weight in self._rx[group]:
            if pattern.search(text):
                best = min(best, weight) if weight < 0 else max(best, weight)
        return best

    def _avoid_score(self, text: str) -> float:
        return min([w for p, w in self._rx["avoid"] if p.search(text)] or [0.0])

    def goal_score(self, el: Element) -> float:
        """How strongly this element represents the user's goal (used by the detector too)."""
        text = el.full_text.lower()
        if self._avoid_score(text) < 0:
            return 0.0
        return max(self._group_score("goal", text), self._group_score("submit", text) if el.is_submit else 0.0)

    def _user_values(self) -> list[str]:
        return [v.lower() for k, v in self.inputs.items() if k in {"order_number", "transaction_id", "booking_reference", "flight_number"} and len(v) >= 4]

    def score_element(self, el: Element, obs: Observation, memory: SessionMemory) -> tuple[float, list[str]]:
        text = el.full_text.lower()
        reasons: list[str] = []
        href_path = urlparse(el.href).path.lower() if el.href else ""
        href_words = re.sub(r"[/_.\-]+", " ", href_path)

        if el.href and not is_allowed_url(el.href):
            return -100.0, ["destination outside the simulation allowlist"]
        if signature(el) in memory.blocked:
            return -100.0, ["previously blocked by the safety agent"]

        goal = self._group_score("goal", text)
        stage = self._group_score("stage", text)
        submit = self._group_score("submit", text) if el.is_submit else 0.0
        decline = 0.0
        if memory.goal_engaged or el.inside_dialog or obs.has_dialog:
            decline = self._group_score("decline", text)
        avoid = min(self._avoid_score(text), self._avoid_score(href_words) * 0.6)
        href_goal = 0.5 * self._group_score("goal", href_words) + 0.3 * self._group_score("stage", href_words)

        score = goal + stage + submit + decline + avoid + href_goal
        for name, value in (("goal", goal), ("stage", stage), ("submit", submit), ("decline", decline), ("avoid", avoid), ("destination", href_goal)):
            if value:
                reasons.append(f"{name} {value:+.1f}")
        if any(v in text or v in href_path for v in self._user_values()):
            score += 6
            reasons.append("matches the user's reference +6")
        repeat = memory.clicks[(obs.path, signature(el))]
        if repeat:
            score -= 8 * repeat
            reasons.append(f"already clicked {repeat}x")
        if href_path and href_path != obs.path:
            visits = memory.page_visits[href_path]
            if visits:
                score -= 3 * visits
                reasons.append(f"destination visited {visits}x")
            if len(memory.history) >= 2 and href_path == memory.history[-2]:
                score -= 3
                reasons.append("returns to the previous page -3")
        elif href_path and href_path == obs.path and el.role == "link":
            score -= 4
            reasons.append("same-page anchor -4")
        if signature(el) in memory.revealed and not el.visible:
            score -= 6
            reasons.append("could not be revealed")
        if obs.has_dialog:
            if el.inside_dialog:
                score += 2
            else:
                score -= 6
        if not el.visible and not el.inside_closed_details:
            score -= 0.5
        if memory.goal_engaged and el.region in ("nav", "header") and goal <= 0:
            score -= 2
            reasons.append("leaves the current flow -2")
        return score, reasons

    # ---------------------------------------------------------------- completion
    def check_completion(self, obs: Observation, memory: SessionMemory) -> Optional[dict[str, Any]]:
        if not memory.submitted:
            return None
        text = obs.visible_text
        if not any(p.search(text) for p in self._success):
            return None
        reference = None
        match = REFERENCE_RE.search(text)
        if match:
            reference = match.group(1)
        result: dict[str, Any] = {"reference": reference, "verified": True, "notes": []}
        if self.task_type == TaskType.REJECT_TRACKING:
            still_on = [line.strip() for line in text.splitlines()
                        if re.search(r":\s*(on|enabled|allowed)\b", line, re.IGNORECASE) and not ESSENTIAL_RE.search(line)]
            if still_on:
                result["verified"] = False
                result["notes"].append("Still enabled after saving: " + "; ".join(still_on))
            else:
                result["notes"].append("Verified on the confirmation page that every non-essential category is off.")
        return result

    # ------------------------------------------------------------- observations
    def collect_facts(self, obs: Observation, memory: SessionMemory) -> None:
        """Record page lines that mention the user's own references (e.g. a charge line)."""
        values = self._user_values()
        if not values:
            return
        for line in obs.visible_text.splitlines():
            low = line.lower()
            if any(v in low for v in values) and 6 < len(line) < 240:
                fact = re.sub(r"\s+", " ", line).strip()
                if fact not in memory.observed_facts:
                    memory.observed_facts.append(fact)

    # ------------------------------------------------------------------ forms
    def _form_fields(self, obs: Observation, form_id: str) -> list[Element]:
        return [e for e in obs.elements if e.form_id == form_id and e.role in FIELD_ROLES and not e.disabled]

    def _submit_buttons(self, obs: Observation, form_id: str) -> list[Element]:
        return [e for e in obs.elements if e.form_id == form_id and e.is_submit and not e.disabled]

    def _submit_score(self, el: Element) -> float:
        text = el.full_text.lower()
        avoid = self._avoid_score(text)
        if avoid < 0:
            return avoid
        return max(self._group_score("submit", text), self._group_score("goal", text))

    def _field_spec(self, el: Element):
        haystack = f"{el.label} {el.name}"
        for spec in self.profile.fields:
            if spec.regex.search(haystack):
                return spec
        return None

    def _choose_option(self, options: list[tuple[str, str]], key: str, value: str, group_label: str) -> Optional[str]:
        """Pick an option value. `options` = [(value, text)]."""
        if not options:
            return None
        low_value = value.lower()
        if key in {"transaction_id", "order_number", "booking_reference"}:
            for opt_value, opt_text in options:
                if low_value and (low_value in opt_text.lower() or low_value == opt_value.lower()):
                    return opt_value
            return None
        if key == "delay_hours" and value:
            try:
                hours = float(value)
            except ValueError:
                hours = None
            if hours is not None:
                for opt_value, opt_text in options:
                    nums = [float(n) for n in re.findall(r"\d+(?:\.\d+)?", opt_text)]
                    t = opt_text.lower()
                    if ("more than" in t or "over" in t or "+" in t) and nums and hours >= nums[0]:
                        return opt_value
                    if ("less than" in t or "under" in t) and nums and hours < nums[0]:
                        return opt_value
                    if len(nums) >= 2 and nums[0] <= hours < nums[1]:
                        return opt_value
        if value:
            words = set(re.findall(r"[a-z]{3,}", low_value))
            best, best_overlap = None, 0
            for opt_value, opt_text in options:
                overlap = len(words & set(re.findall(r"[a-z]{3,}", opt_text.lower())))
                if overlap > best_overlap:
                    best, best_overlap = opt_value, overlap
            if best is not None:
                return best
        return None

    def _preference_for(self, group_label: str) -> Optional[tuple[str, str]]:
        for group_pattern, preferred, avoided in self.profile.choice_preferences:
            if re.search(group_pattern, group_label, re.IGNORECASE):
                return preferred, avoided
        return None

    def _desired_choice(self, group_label: str, options: list[tuple[str, str]], current: Optional[str], required: bool, el: Element) -> tuple[Optional[str], str]:
        """Return (desired option value, explanation) for a select/radio group."""
        spec = self._field_spec(el)
        if spec and spec.key in self.inputs:
            choice = self._choose_option(options, spec.key, self.inputs[spec.key], group_label)
            if choice is not None:
                return choice, f"matches your '{spec.key}'"
            if spec.key in {"transaction_id", "order_number", "booking_reference"}:
                return None, f"MISSING:{spec.key} not offered by the site"
        pref = self._preference_for(group_label)
        if pref:
            preferred, avoided = pref
            for opt_value, opt_text in options:
                if preferred and re.search(preferred, opt_text, re.IGNORECASE):
                    if current != opt_value:
                        return opt_value, f"chose '{opt_text}' (in your interest) over the default"
                    return opt_value, "already in your interest"
        if current not in (None, ""):
            return current, "kept existing choice"
        if required or spec:
            for opt_value, opt_text in options:
                if re.search(NEUTRAL_CHOICE, opt_text, re.IGNORECASE):
                    return opt_value, f"answered unrelated required question minimally ('{opt_text}')"
            if spec and spec.key == "reason":
                for opt_value, opt_text in options:
                    if opt_value and re.search(r"other", opt_text, re.IGNORECASE):
                        return opt_value, "no option matches your reason; chose 'Other'"
            if required:
                return None, "MISSING:" + (group_label or el.name or "required choice")
        return current, ""

    def plan_form(self, obs: Observation, form_id: str, memory: SessionMemory) -> tuple[Optional[ProposedAction], list[str]]:
        """Return the next field action needed in this form (or None when ready) and missing inputs."""
        missing: list[str] = []
        fields = self._form_fields(obs, form_id)
        handled_radio_groups: set[str] = set()
        for el in fields:
            attempt_key = (obs.path, form_id, el.name or el.fc_id, el.value if el.role == "radio" else "")
            if memory.field_attempts[attempt_key] >= 2:
                continue  # tried twice already - do not loop on a stubborn field
            label = el.full_text or el.name
            if el.role in ("checkbox", "switch"):
                desired = el.checked
                why = ""
                if self.task_type == TaskType.REJECT_TRACKING and not ESSENTIAL_RE.search(label):
                    desired, why = False, "non-essential tracking - refuse"
                elif self._uncheck.search(label) and not self._check.search(label):
                    desired, why = False, "pre-selected option the user did not ask for"
                elif el.required and self._check.search(label):
                    desired, why = True, "required declaration (shown to you before submitting)"
                if desired is not None and desired != el.checked:
                    if not el.visible:
                        return ProposedAction(kind="reveal", element_id=el.fc_id, goal_step="reveal",
                                              rationale=f"Reveal hidden option '{label[:60]}' to change it"), missing
                    memory.field_attempts[attempt_key] += 1
                    return ProposedAction(kind="check" if desired else "uncheck", element_id=el.fc_id,
                                          goal_step="prepare_form", rationale=f"{'Tick' if desired else 'Untick'} '{label[:70]}': {why}"), missing
                continue
            if el.role == "radio":
                if el.name in handled_radio_groups:
                    continue
                handled_radio_groups.add(el.name)
                group = [e for e in fields if e.role == "radio" and e.name == el.name]
                options = [(e.value, e.label or e.text) for e in group]
                current = next((e.value for e in group if e.checked), None)
                group_label = re.sub(r".*\[group: ([^\]]*)\].*", r"\1", el.label) if "[group:" in el.label else el.name
                desired, why = self._desired_choice(group_label, options, current, any(e.required for e in group), el)
                if why.startswith("MISSING:"):
                    missing.append(why[8:])
                    continue
                if desired is not None and desired != current:
                    target = next(e for e in group if e.value == desired)
                    memory.field_attempts[(obs.path, form_id, target.name or target.fc_id, target.value)] += 1
                    return ProposedAction(kind="check", element_id=target.fc_id, goal_step="prepare_form",
                                          rationale=f"Select '{(target.label or target.value)[:60]}' for '{group_label[:50]}': {why}"), missing
                continue
            if el.role == "select":
                options = [(o["value"], o["text"]) for o in el.options]
                desired, why = self._desired_choice(el.label, options, el.value, el.required, el)
                if why.startswith("MISSING:"):
                    missing.append(why[8:])
                    continue
                if desired is not None and desired != el.value:
                    memory.field_attempts[attempt_key] += 1
                    return ProposedAction(kind="select", element_id=el.fc_id, value=desired, goal_step="prepare_form",
                                          rationale=f"Choose option for '{el.label[:50]}': {why}"), missing
                continue
            # Text inputs
            if is_sensitive_field(label):
                if el.required:
                    missing.append(f"{label[:40]} (sensitive - FairClick never fills this)")
                continue
            spec = self._field_spec(el)
            if spec and spec.key in self.inputs:
                desired_text = self.inputs[spec.key]
                if el.value.strip() != desired_text:
                    memory.field_attempts[attempt_key] += 1
                    return ProposedAction(kind="fill", element_id=el.fc_id, value=desired_text, field_key=spec.key,
                                          goal_step="prepare_form",
                                          rationale=f"Fill '{label[:50]}' with your {spec.key.replace('_', ' ')}"), missing
            elif el.required and not el.value.strip():
                missing.append(label[:60] or el.name)
        return None, missing

    def _relevant_forms(self, obs: Observation) -> list[tuple[float, str, Element]]:
        ranked = []
        for form in obs.forms:
            buttons = [b for b in self._submit_buttons(obs, form["id"])]
            scored = [(self._submit_score(b), b) for b in buttons]
            scored = [(s, b) for s, b in scored if s >= MIN_SCORE]
            if scored:
                s, b = max(scored, key=lambda t: t[0])
                action_words = re.sub(r"[/_.\-]+", " ", urlparse(form["action"]).path.lower())
                if self._avoid_score(action_words) < 0:
                    continue  # form posts to an offer/upsell endpoint
                ranked.append((s, form["id"], b))
        return sorted(ranked, key=lambda t: -t[0])

    # ----------------------------------------------------------------- deciding
    def decide(self, obs: Observation, memory: SessionMemory) -> ProposedAction:
        self.collect_facts(obs, memory)
        missing_required = [k for k in self.profile.required_inputs if k not in self.inputs]
        if missing_required:
            return ProposedAction(kind="need_info", missing=missing_required,
                                  rationale="The task needs information only you can provide.")

        # 1. Candidate clickable elements (links / buttons, excluding form submits).
        candidates: list[tuple[float, Element, list[str]]] = []
        for el in obs.elements:
            if el.role not in CLICKABLE_ROLES or el.is_submit or el.disabled:
                continue
            if obs.has_dialog and not el.inside_dialog and el.visible:
                continue
            score, reasons = self.score_element(el, obs, memory)
            candidates.append((score, el, reasons))
        candidates.sort(key=lambda t: -t[0])
        best_link = candidates[0] if candidates and candidates[0][0] >= MIN_SCORE else None

        # 2. Forms that move towards the goal.
        forms = [] if obs.has_dialog and not any(e.inside_dialog and e.is_submit for e in obs.elements) else self._relevant_forms(obs)
        if forms:
            form_score, form_id, submit = forms[0]
            if memory.goal_engaged:
                form_score += 3  # a form inside the goal flow is how the flow continues
            if best_link is None or form_score >= best_link[0] - 1 or form_score >= 8:
                # Prepare every field first (also for "Reject all", so the data the user
                # approves matches what is sent, even if the site ignores the button).
                action, missing = self.plan_form(obs, form_id, memory)
                if action:
                    return action
                if missing:
                    return ProposedAction(kind="need_info", missing=missing,
                                          rationale="The form requires information you have not provided.")
                if not submit.visible:
                    return ProposedAction(kind="reveal", element_id=submit.fc_id, goal_step="reveal", score=form_score,
                                          rationale=f"'{submit.full_text[:60]}' exists but is hidden - revealing it")
                return ProposedAction(kind="click", element_id=submit.fc_id, score=form_score, goal_step="submit",
                                      rationale=f"Form is prepared; '{submit.full_text[:60]}' completes the user's goal")

        # 3. Otherwise follow the best-scoring link/button.
        if best_link:
            score, el, reasons = best_link
            step = "decline_offer" if self._group_score("decline", el.full_text.lower()) and not self._group_score("goal", el.full_text.lower()) else "navigate"
            if not el.visible:
                return ProposedAction(kind="reveal", element_id=el.fc_id, score=score, goal_step="reveal",
                                      rationale=f"Best match '{el.full_text[:60]}' is hidden - revealing it ({', '.join(reasons)})")
            return ProposedAction(kind="click", element_id=el.fc_id, score=score, goal_step=step,
                                  rationale=f"'{el.full_text[:60]}' best matches the goal ({', '.join(reasons)})")

        # 4. Dead end: go back a step, then give up.
        if memory.backtracks < 3 and len(memory.history) > 1:
            memory.backtracks += 1
            return ProposedAction(kind="back", rationale="No element on this page moves towards the goal; going back.")
        return ProposedAction(kind="fail", rationale="Could not find a path to the goal on this website.")

    # ---------------------------------------------------------------- approvals
    def approval_content(self, obs: Observation, submit: Element, form_values: list[dict[str, Any]], site_name: str) -> dict[str, Any]:
        visible_values = [f for f in form_values if not f.get("hidden")]
        hidden_values = [f for f in form_values if f.get("hidden")]
        data = {"fields": [{"label": (f["label"] or f["name"])[:80], "value": str(f["value"])[:300]} for f in visible_values]}
        if hidden_values:
            data["hidden_fields_set_by_website"] = [{"name": f["name"], "value": str(f["value"])[:120]} for f in hidden_values]
        return {
            "action_summary": f"{self.profile.title} on {site_name}: click '{submit.full_text[:80]}'",
            "reason": f"Your goal: {self.profile.objective} This button submits the request to the website and cannot be undone by FairClick.",
            "data": data,
            "consequences": self.profile.consequences,
            "target_label": submit.full_text[:120],
        }

    # ------------------------------------------------------------ prepared docs
    def prepared_document(self, site_name: str, reference: Optional[str], memory: SessionMemory) -> Optional[str]:
        if self.task_type not in (TaskType.DISPUTE_CHARGE, TaskType.CLAIM_COMPENSATION, TaskType.REQUEST_REFUND):
            return None
        lines: list[str] = []
        if self.task_type == TaskType.DISPUTE_CHARGE:
            lines += [
                "CHARGE DISPUTE SUMMARY (prepared by FairClick - review before use)",
                f"Merchant: {site_name}",
                f"Transaction ID: {self.inputs.get('transaction_id', '')}",
                f"Reason: {self.inputs.get('reason', '')}",
            ]
            if self.inputs.get("details"):
                lines.append(f"Details: {self.inputs['details']}")
            lines.append(f"Merchant dispute reference: {reference or 'not shown by the merchant'}")
            if memory.observed_facts:
                lines.append("Charge details as displayed by the merchant (copied verbatim, not inferred):")
                lines += [f"  - {fact}" for fact in memory.observed_facts[:5]]
            lines += ["", "Next steps (general guidance, not legal advice): if the merchant does not resolve the dispute, "
                          "you can contact your card issuer and provide this summary and the evidence screenshots. "
                          "Card issuers set their own time limits for disputes."]
        elif self.task_type == TaskType.CLAIM_COMPENSATION:
            lines += [
                "COMPENSATION CLAIM SUMMARY (prepared by FairClick - review before use)",
                f"Provider: {site_name}",
                f"Booking reference: {self.inputs.get('booking_reference', '')}",
                f"Flight: {self.inputs.get('flight_number', '')}" + (f" on {self.inputs['flight_date']}" if self.inputs.get("flight_date") else ""),
                f"Passenger: {self.inputs.get('passenger_name', '')}",
            ]
            if self.inputs.get("delay_hours"):
                lines.append(f"Arrival delay reported by you: {self.inputs['delay_hours']} hours")
            lines.append(f"Claim reference: {reference or 'not shown by the provider'}")
            lines.append("Requested settlement: payment (not a voucher).")
            if memory.observed_facts:
                lines.append("Trip details as displayed by the provider (copied verbatim):")
                lines += [f"  - {fact}" for fact in memory.observed_facts[:5]]
            lines += ["", "General guidance (not legal advice): passenger-rights rules such as EU Regulation 261/2004 may "
                          "entitle passengers to compensation for long delays depending on distance, delay length and the "
                          "cause of the disruption. FairClick does not determine eligibility or amounts."]
        else:
            lines += [
                "REFUND REQUEST SUMMARY (prepared by FairClick)",
                f"Merchant: {site_name}",
                f"Order: {self.inputs.get('order_number', '')}",
                f"Reason: {self.inputs.get('reason', '')}",
                f"Request reference: {reference or 'not shown by the merchant'}",
            ]
            if memory.observed_facts:
                lines.append("Order details as displayed by the merchant (copied verbatim):")
                lines += [f"  - {fact}" for fact in memory.observed_facts[:5]]
        return "\n".join(lines)
