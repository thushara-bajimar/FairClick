"""Agent 2 - Dark Pattern Detection Agent (rule-based, evidence-driven).

Every detection is derived from something observable on the page: wording,
computed styles (size, contrast), default form state, element visibility,
link destinations, timer behaviour or repetition across the session. The site
identity is never used as a signal.
"""
from __future__ import annotations

import re
from typing import Any, Callable, Optional
from urllib.parse import urlparse

from .models import Detection, Element, Observation
from .taxonomy import TAXONOMY

DECLINE_START = re.compile(r"^\s*(no\b|nope|nah|not now|skip|i('?m| am)? ?(ok|okay|fine)|i (don'?t|do not|prefer|'?d rather|like|will|'?ll)|i'?d rather|continue without|maybe later)", re.IGNORECASE)
SHAME_WORDS = re.compile(
    r"\b(losing|lose|lost|miss(ing)? out|don'?t care|do not care|hate|prefer (to )?(pay|lose|miss|stay)|full price|"
    r"pay more|unhealthy|out of shape|give up|regret|boring|without (my|the) benefits|no benefits|don'?t want to save|"
    r"rather pay|okay losing|ok losing|fine losing|my progress|my streak|stay (uninformed|unprotected)|risk|"
    r"don'?t (like|want) (deals|savings|money)|bad decisions?)\b",
    re.IGNORECASE,
)
URGENCY = re.compile(
    r"\b(only|just) \d+ (minutes?|mins?|seconds?|hours?|seats?|items?|spots?)( left| remaining)?\b|\bhurry\b|\bact (now|fast)\b|"
    r"\blast chance\b|\b(offer|deal|price|window|this) (ends|expires|closes)\b|\bexpires? in\b|\bends? in\b|"
    r"\bcloses? in\b|\blimited[- ]time\b|\b(accept|act|respond|decide|buy|claim|order|book)\b[^.!]{0,30}\bimmediately\b|\bdon'?t miss\b|\bbefore it'?s gone\b|\bprices? (will )?(rise|go up|increase)\b|"
    r"\b(only|just) \d+ left\b|\bselling fast\b|\btoday only\b",
    re.IGNORECASE,
)
TIMER = re.compile(r"\b\d{1,2}:\d{2}(:\d{2})?\b")
FINE_PRINT_TERMS = re.compile(
    r"auto(matically)?[- ]?renew|renews? automatically|every (month|year)|recurring|will be (charged|billed)|billed (automatically|monthly|annually)|"
    r"(per|a|/) ?(month|mo|year|yr)\b|non-?refundable|restocking|fee|waive|forfeit|after (the |your )?trial|then \$|then €|"
    r"processing charge|no cash|voucher only|terms apply|cancel(lation)? (fee|charge)",
    re.IGNORECASE,
)
_NOT_END = r"(?:[^.]|\.\d)"  # any char except a sentence-ending full stop (keeps "$29.99")
CONTINUITY = re.compile(
    r"(free|trial|\$1\b|€1\b|discount|special offer|intro(ductory)? (price|offer)|\d+% off)" + _NOT_END + r"{0,120}"
    r"(then|after (which|that)|automatically|auto-?renew|renews?|will be (charged|billed)|billed)|"
    r"(will be|are) (charged|billed)" + _NOT_END + r"{0,60}unless you cancel|"
    r"(automatically|auto-?)\s?renews?" + _NOT_END + r"{0,60}(\$|€|£)\s?\d|"
    r"after (the first |your first )?\d+ (days?|weeks?|months?)" + _NOT_END + r"{0,80}(\$|€|£)\s?\d|"
    r"\bthen (\$|€|£)\s?\d+(\.\d+)?\s?(/|per |a )\s?(month|mo|year|yr|week)",
    re.IGNORECASE,
)
PRESELECT_LABEL = re.compile(
    r"analytic|advertis|personali[sz]|marketing|partner|tracking|social media|newsletter|deals|offers|promotion|"
    r"share|third[- ]part|insurance|priority|voucher|store credit|waive|legitimate interest|free month|instead of|"
    r"add-?on|protection|recommend|updates",
    re.IGNORECASE,
)
ESSENTIAL = re.compile(r"strictly necessary|essential|required", re.IGNORECASE)
BUSINESS_CHOICE = re.compile(r"store credit|voucher|gift card|points|miles|free month|credit instead|exchange", re.IGNORECASE)
CONSUMER_CHOICE = re.compile(r"original payment|bank|card|cash|refund to|transfer|money back", re.IGNORECASE)
ACCEPTISH = re.compile(r"\b(accept|allow|agree|keep|stay|claim|get|yes|upgrade|continue with offer|take (the|this|my)|resume|start)\b", re.IGNORECASE)
DECLINEISH = re.compile(r"\b(reject|decline|cancel|no thanks|no,|not now|settings|manage|customi[sz]e|turn off|skip|end|leave|options|refuse|continue to)\b", re.IGNORECASE)
RETENTION = re.compile(
    r"before you (go|leave|cancel)|wait[!,.]|are you (sure|absolutely sure)|we'?d hate to see you go|special offer|"
    r"\d+% off|instead\b|don'?t go|last chance|reconsider|you('?ll| will) lose|exclusive offer",
    re.IGNORECASE,
)
FORCED = re.compile(
    r"(you must|you need to|required to|please) (complete|answer|fill( out)?|take|create|chat|call|speak|watch|confirm)[^.]{0,80}"
    r"(before|to continue|in order to|to proceed|to request|to cancel|to submit)",
    re.IGNORECASE,
)
UNRELATED_REQUIRED = re.compile(r"survey|\brate\b|\brating\b|satisf|how likely|why are you leaving|date of birth|\bphone\b|\bmobile\b|how did you hear|marketing", re.IGNORECASE)
GOAL_WORDS = re.compile(r"cancel|refund|return|reject|decline|claim|compensation|dispute|turn off|end membership", re.IGNORECASE)
NEGATION = re.compile(r"\b(?:not|no|don'?t|doesn'?t|unless|non-?\w+|un\w+ing|disable|object|opt(?:ing)? out)\b", re.IGNORECASE)
MISLEAD_DEST = re.compile(r"offer|upgrade|pause|retain|retention|voucher|deal|exchange|promo|discount|special", re.IGNORECASE)


def _prominence(el: Element) -> float:
    contrast_factor = min(el.contrast, 7.0) / 7.0
    weight_factor = 1.25 if el.font_weight >= 600 else 1.0
    return max(el.area, 1.0) * max(contrast_factor, 0.05) * el.opacity * weight_factor


def _make(category: str, evidence: str, location: str, severity: str, confidence: float, obs: Observation,
          element_id: str = "", description: str = "", extra: Optional[dict[str, Any]] = None) -> Detection:
    info = TAXONOMY[category]
    return Detection(
        category=category,
        pattern_name=info["name"],
        description=description or info["description"],
        evidence=evidence[:500],
        location=location,
        severity=severity,
        confidence=round(confidence, 2),
        recommendation=info["recommendation"],
        element_id=element_id,
        page_url=obs.url,
        page_path=obs.path,
        extra=extra or {},
    )


def _loc(el: Element) -> str:
    where = {"dialog": "pop-up dialog", "banner": "consent banner", "footer": "page footer", "nav": "navigation menu", "header": "page header"}.get(el.region, "main content")
    state = "" if el.visible else (", inside a collapsed section" if el.inside_closed_details else ", not visible")
    return f"{el.descriptor} in {where} (x={int(el.x)}, y={int(el.y)}{state})"


class DarkPatternDetectionAgent:
    name = "detector"

    def __init__(self, goal_scorer: Callable[[Element], float]) -> None:
        self.goal_scorer = goal_scorer
        self.retention_pages: list[str] = []
        self.first_states: dict[tuple[str, str, str], Optional[bool]] = {}
        self.modified: set[tuple[str, str, str]] = set()
        self._reported: set[tuple[str, ...]] = set()

    def _once(self, *key: str) -> bool:
        """True the first time a (check, page, subject) combination is seen."""
        if key in self._reported:
            return False
        self._reported.add(key)
        return True

    def note_modified(self, obs: Observation, el: Element) -> None:
        """Called when the agent itself changes a field, so it is not reported as a site default."""
        self.modified.add((obs.path, el.name, el.value))

    # ------------------------------------------------------------------ analyse
    def analyze(self, obs: Observation) -> list[Detection]:
        detections: list[Detection] = []
        for check in (self._confirm_shaming, self._fake_urgency, self._pre_selection, self._interface_interference,
                      self._hidden_information, self._forced_continuity, self._obstruction, self._misdirection,
                      self._forced_action, self._nagging):
            detections.extend(check(obs))
        return detections

    def _clickables(self, obs: Observation) -> list[Element]:
        return [e for e in obs.elements if e.role in ("button", "link", "summary", "menuitem") and (e.text or e.label)]

    def _confirm_shaming(self, obs: Observation) -> list[Detection]:
        out = []
        for el in self._clickables(obs):
            text = el.full_text
            if len(text) > 160 or not SHAME_WORDS.search(text):
                continue
            starts_decline = bool(DECLINE_START.search(text))
            confidence = 0.92 if starts_decline else 0.7
            out.append(_make("confirm_shaming", f"Decline option reads: \"{text}\"", _loc(el), "medium", confidence, obs, el.fc_id,
                             extra={"decline_phrasing": starts_decline}))
        return out

    def _fake_urgency(self, obs: Observation) -> list[Detection]:
        out = []
        seen = set()
        for block in obs.text_blocks:
            if not block.visible or len(block.text) > 400:
                continue
            match = URGENCY.search(block.text)
            if not match or block.text in seen:
                continue
            seen.add(block.text)
            has_timer = any(TIMER.search(t["text"]) for t in obs.timers)
            out.append(_make("fake_urgency", f"Urgency message: \"{block.text[:200]}\"", f"{block.tag} text in {block.region}",
                             "medium", 0.75 if has_timer else 0.6, obs, block.fc_id, extra={"needs_timer_probe": has_timer}))
        return out

    def timer_probe_detection(self, obs: Observation, timer: dict[str, Any], probe: dict[str, Any]) -> Optional[Detection]:
        if not probe:
            return None
        if probe["reset_on_reload"]:
            evidence = (f"Countdown \"{timer['text'][:80]}\" read {probe['first']}s, then {probe['second']}s, "
                        f"and restarted at {probe['after_reload']}s after reloading the page - the deadline is not real.")
            return _make("fake_urgency", evidence, "countdown timer", "high", 0.95, obs, timer["id"],
                         description="Countdown timer resets on reload: the urgency is fabricated.", extra={"probe": probe})
        return None

    def _pre_selection(self, obs: Observation) -> list[Detection]:
        out = []
        for el in obs.elements:
            if el.role not in ("checkbox", "radio", "switch") or not el.checked:
                continue
            key = (obs.path, el.name, el.value)
            if key in self.modified:
                continue
            label = el.full_text or el.name
            if el.role == "radio":
                group = [e for e in obs.elements if e.role == "radio" and e.name == el.name and e.form_id == el.form_id]
                if BUSINESS_CHOICE.search(label) and any(CONSUMER_CHOICE.search(e.full_text) for e in group if e is not el):
                    out.append(_make("pre_selection", f"Option \"{label[:140]}\" is selected by default although a refund/payment option exists",
                                     _loc(el), "high", 0.9, obs, el.fc_id))
                continue
            if el.disabled or ESSENTIAL.search(label) and not PRESELECT_LABEL.search(label.replace("required", "")):
                continue
            if PRESELECT_LABEL.search(label):
                out.append(_make("pre_selection", f"Checkbox \"{label[:160]}\" is ticked by default", _loc(el), "high", 0.9, obs, el.fc_id))
        return out

    def _interface_interference(self, obs: Observation) -> list[Detection]:
        visible = [e for e in self._clickables(obs) if e.visible and e.area > 0]
        if obs.has_dialog:
            visible = [e for e in visible if e.inside_dialog]
        accepts = [e for e in visible if ACCEPTISH.search(e.full_text) and not DECLINEISH.search(e.full_text)]
        declines = [e for e in visible if DECLINEISH.search(e.full_text) or DECLINE_START.search(e.full_text) or self.goal_scorer(e) > 0]
        if not accepts or not declines:
            return []
        top_accept = max(accepts, key=_prominence)
        weakest_decline = min(declines, key=_prominence)
        ratio = _prominence(top_accept) / max(_prominence(weakest_decline), 1.0)
        low_contrast = weakest_decline.contrast < 3.0 <= top_accept.contrast
        if ratio < 4 and not low_contrast:
            return []
        if not self._once("interference", obs.path):
            return []
        evidence = (f"\"{top_accept.full_text[:60]}\" ({int(top_accept.area)}px², contrast {top_accept.contrast}:1, {top_accept.font_size:.0f}px) vs "
                    f"\"{weakest_decline.full_text[:60]}\" ({int(weakest_decline.area)}px², contrast {weakest_decline.contrast}:1, "
                    f"{weakest_decline.font_size:.0f}px) - visual weight ratio {ratio:.1f}x")
        return [_make("interface_interference", evidence, _loc(weakest_decline), "medium" if ratio < 10 else "high",
                      min(0.95, 0.6 + ratio / 40 + (0.15 if low_contrast else 0)), obs, top_accept.fc_id)]

    def _hidden_information(self, obs: Observation) -> list[Detection]:
        out = []
        for block in obs.text_blocks:
            if not FINE_PRINT_TERMS.search(block.text) or len(block.text) > 500:
                continue
            small = 0 < block.font_size <= 11
            faint = 1.3 <= block.contrast < 3.0
            if (small or faint) and block.visible:
                out.append(_make("hidden_information", f"Fine print ({block.font_size:.0f}px, contrast {block.contrast}:1): \"{block.text[:220]}\"",
                                 f"{block.tag} text in {block.region}", "high" if small and faint else "medium",
                                 0.85 if small and faint else 0.7, obs, block.fc_id))
        return out

    def _forced_continuity(self, obs: Observation) -> list[Detection]:
        out, seen = [], set()
        for block in obs.text_blocks:
            if not block.visible or len(block.text) > 500:
                continue
            match = CONTINUITY.search(block.text)
            if match and block.text not in seen:
                seen.add(block.text)
                hidden = block.font_size <= 11 or block.contrast < 3
                out.append(_make("forced_continuity", f"\"{block.text[:240]}\"", f"{block.tag} text in {block.region}",
                                 "high" if hidden else "medium", 0.85 if hidden else 0.7, obs, block.fc_id))
        return out

    def _obstruction(self, obs: Observation) -> list[Detection]:
        out = []
        clickables = self._clickables(obs)
        goal_elements = [(self.goal_scorer(e), e) for e in clickables]
        goal_elements = [(s, e) for s, e in goal_elements if s >= 5]
        if not goal_elements:
            return out
        others = [e for e in clickables if e.visible and e.area > 0 and ACCEPTISH.search(e.full_text)]
        for score, el in goal_elements:
            reasons = []
            if not el.visible:
                reasons.append("collapsed inside a closed section" if el.inside_closed_details else "not visible until a menu is opened")
            else:
                if el.contrast < 3.0:
                    reasons.append(f"low contrast {el.contrast}:1")
                if 0 < el.font_size <= 11:
                    reasons.append(f"small {el.font_size:.0f}px text")
                if el.region == "footer":
                    reasons.append("placed in the footer")
                if others and max(_prominence(o) for o in others) > 6 * _prominence(el):
                    reasons.append("far less prominent than the alternative offers")
            if reasons and self._once("obstruction", obs.path, el.full_text[:60]):
                out.append(_make("obstruction", f"The option the user needs, \"{el.full_text[:80]}\", is {', '.join(reasons)}",
                                 _loc(el), "high", 0.85 if len(reasons) > 1 or not el.visible else 0.7, obs, el.fc_id))
        return out[:2]

    def _misdirection(self, obs: Observation) -> list[Detection]:
        out = []
        for el in self._clickables(obs):
            if not el.href:
                continue
            dest = urlparse(el.href).path.lower()
            if GOAL_WORDS.search(el.full_text) and MISLEAD_DEST.search(dest) and not GOAL_WORDS.search(dest):
                out.append(_make("misdirection", f"Link labelled \"{el.full_text[:80]}\" actually leads to {dest}", _loc(el),
                                 "high", 0.9, obs, el.fc_id))
        # Trick wording: several negations in one sentence about consent/choices.
        for block in obs.text_blocks:
            if not block.visible or not re.search(r"consent|cookie|opt|tick|object|choice|process", block.text, re.IGNORECASE):
                continue
            for sentence in re.split(r"(?<=[.!?])\s+", block.text):
                negations = NEGATION.findall(sentence)
                if len(negations) >= 3 and self._once("trick", obs.path, sentence[:60]):
                    out.append(_make("misdirection", f"Confusing wording with {len(negations)} negations: \"{sentence[:220]}\"",
                                     f"{block.tag} text in {block.region}", "medium", 0.7, obs, block.fc_id,
                                     description="Trick question: consent wording uses multiple negatives so the outcome of a choice is unclear."))
        # The business-favourable option promoted as "recommended"/"instant".
        for el in obs.elements:
            if el.role == "radio" and BUSINESS_CHOICE.search(el.full_text) and re.search(r"recommended|instant|fastest|best|popular", el.full_text, re.IGNORECASE):
                out.append(_make("misdirection", f"Option promoted as \"{el.full_text[:120]}\" steers away from a cash refund", _loc(el),
                                 "medium", 0.75, obs, el.fc_id))
        # In a cancellation/refund/claim flow, the visually primary action is an offer.
        if GOAL_WORDS.search(obs.path):
            visible = [e for e in self._clickables(obs) if e.visible and e.area > 0]
            if visible:
                primary = max(visible, key=_prominence)
                if ACCEPTISH.search(primary.full_text) and re.search(r"offer|%|off|free|deal|keep|stay|voucher|pause|switch", primary.full_text, re.IGNORECASE)                         and self._once("primary-offer", obs.path):
                    out.append(_make("misdirection", f"Primary button in a {GOAL_WORDS.search(obs.path).group(0)} flow is \"{primary.full_text[:80]}\"",
                                     _loc(primary), "medium", 0.7, obs, primary.fc_id))
        return out

    def _forced_action(self, obs: Observation) -> list[Detection]:
        out = []
        for block in obs.text_blocks:
            if block.visible and FORCED.search(block.text) and len(block.text) < 400:
                out.append(_make("forced_action", f"\"{block.text[:220]}\"", f"{block.tag} text in {block.region}", "medium", 0.75, obs, block.fc_id))
                break
        required_unrelated = [e for e in obs.elements if e.required and e.role in ("radio", "select", "textbox", "checkbox")
                              and UNRELATED_REQUIRED.search(e.full_text or e.name)]
        if required_unrelated:
            el = required_unrelated[0]
            out.append(_make("forced_action", f"Required field unrelated to the request: \"{(el.full_text or el.name)[:140]}\"",
                             _loc(el), "medium", 0.8, obs, el.fc_id))
        return out

    def _nagging(self, obs: Observation) -> list[Detection]:
        dialog_text = " ".join(e.full_text for e in obs.elements if e.inside_dialog)
        page_text = obs.visible_text[:3000]
        is_retention = bool(RETENTION.search(page_text)) and bool(GOAL_WORDS.search(obs.path) or obs.has_dialog)
        if not is_retention:
            return []
        if obs.path not in self.retention_pages:
            self.retention_pages.append(obs.path)
        out = []
        if obs.has_dialog and RETENTION.search(dialog_text + " " + page_text):
            out.append(_make("nagging", "A pop-up interrupted the task to repeat a retention offer/warning",
                             "pop-up dialog", "medium", 0.75, obs,
                             next((e.fc_id for e in obs.elements if e.inside_dialog), "")))
        count = len(self.retention_pages)
        if count >= 2:
            out.append(_make("nagging", f"Retention screen #{count} in this session ({' -> '.join(self.retention_pages[-4:])})",
                             "page content", "medium" if count < 4 else "high", min(0.95, 0.6 + 0.1 * count), obs))
        return out
