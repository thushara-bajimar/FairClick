"""Goal profiles: what each consumer-rights task is trying to achieve.

These are *generic* across websites - they describe the user's intent in terms
of vocabulary and form semantics, not site-specific click sequences.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from .models import TaskType

Weighted = list[tuple[str, float]]


def _compile(terms: Weighted) -> list[tuple[re.Pattern[str], float]]:
    return [(re.compile(t, re.IGNORECASE), w) for t, w in terms]


# Offers, purchases and upsells: an agent acting for the user never selects these.
COMMON_AVOID: Weighted = [
    (r"\baccept( all| the| this)?( offer| deal| voucher| cookies)?\b", -12),
    (r"\b(claim|get|grab|unlock)( my| this| the| your)? (\d+% off|offer|deal|discount|free month|bonus|voucher)", -12),
    (r"\b(upgrade|buy|purchase|add to cart|checkout|pay now|subscribe|start (free )?trial|renew now)\b", -12),
    (r"\b(keep|stay|resume|remain)\b( my| me| on| pro| premium| subscribed| member)?", -9),
    (r"\b(pause|switch|downgrade|change plan|exchange)\b", -6),
    (r"\byes,? (please|i want|give|keep|i'?ll)", -9),
    (r"\b(allow|agree|i agree|ok,? got it|got it)\b", -8),
    (r"\b(rebook|travel credit|voucher|store credit|gift card)\b", -6),
    (r"\b(sign out|log ?out|delete account|share|tweet|facebook)\b", -6),
]

# Ways of declining an interstitial offer / retention screen to keep going.
DECLINE_TERMS: Weighted = [
    (r"\bno,? thanks\b", 4.0),
    (r"\b(continue|proceed|go on) (to|with)( my)? (cancel|cancellation|refund|claim|dispute|request)", 6.0),
    (r"\b(still want to|i want to|i'd like to) (cancel|leave|end|continue|request|claim|dispute)", 5.0),
    (r"\b(decline|skip|not now|no,? continue|dismiss)\b", 3.0),
    (r"^\s*(×|x|close)\s*$", 2.0),
    (r"\bi don'?t (care|want|need)\b", 2.5),
    (r"\bi('?m| am) (ok|okay|fine)\b", 2.5),
    (r"\bno,? (continue|i'?ll|i prefer|i don)", 3.5),
]


@dataclass
class FieldSpec:
    key: str                     # task input key
    label_pattern: str           # matches field label / name
    kind: str = "text"           # text | choice
    required_input: bool = False

    @property
    def regex(self) -> re.Pattern[str]:
        return re.compile(self.label_pattern, re.IGNORECASE)


@dataclass
class GoalProfile:
    task_type: TaskType
    title: str
    objective: str
    goal_terms: Weighted
    stage_terms: Weighted
    submit_terms: Weighted
    success_patterns: list[str]
    fields: list[FieldSpec] = field(default_factory=list)
    # Choice preferences for radio groups/selects: (group pattern, preferred, avoided)
    choice_preferences: list[tuple[str, str, str]] = field(default_factory=list)
    uncheck_pattern: str = (
        r"newsletter|marketing|promotion|deals|offers|partner|advertis|personali[sz]|analytic|tracking|"
        r"social media|third[- ]part|share my|insurance|priority|voucher|store credit|waive|legitimate interest|"
        r"free month instead|instead of a refund|add-?on|upsell|recommend"
    )
    check_pattern: str = r"i confirm|accurate|true and correct|i declare|i understand"
    avoid_terms: Weighted = field(default_factory=lambda: list(COMMON_AVOID))
    required_inputs: list[str] = field(default_factory=list)
    consequences: str = ""

    def compiled(self) -> dict[str, list[tuple[re.Pattern[str], float]]]:
        return {
            "goal": _compile(self.goal_terms),
            "stage": _compile(self.stage_terms),
            "submit": _compile(self.submit_terms),
            "decline": _compile(DECLINE_TERMS),
            "avoid": _compile(self.avoid_terms),
        }


NEUTRAL_CHOICE = r"prefer not to (say|answer)|no particular reason|rather not say|don'?t know|not sure|skip|\bother\b"

PROFILES: dict[TaskType, GoalProfile] = {
    TaskType.CANCEL_SUBSCRIPTION: GoalProfile(
        task_type=TaskType.CANCEL_SUBSCRIPTION,
        title="Cancel subscription",
        objective="End the paid subscription / turn off automatic renewal without accepting any offer.",
        goal_terms=[
            (r"\bcancel( my)? (membership|subscription|plan|account|pro|premium)\b", 9),
            (r"\bturn off auto-?renew(al)?\b|\bend (my )?(membership|subscription)\b|\bstop (my )?subscription\b", 9),
            (r"\bcancel\b", 5),
            (r"\bcancell?ation\b", 4),
        ],
        stage_terms=[
            (r"\b(manage|my) (subscription|membership|plan)\b", 5),
            (r"\b(subscription|membership)( & | and )?(billing|settings|details)?\b", 3.5),
            (r"\baccount( settings)?\b|\bprofile\b", 2.5),
            (r"\bbilling\b|\bplan\b|\bsettings\b", 2),
            (r"\bmore (options|membership options)\b|\bother options\b", 2.5),
        ],
        submit_terms=[
            (r"\b(yes,? )?(cancel|end) (my )?(membership|subscription|plan)\b", 10),
            (r"\bconfirm (cancell?ation|cancel)\b|\bturn off auto-?renew(al)?\b|\bfinish cancell?ation\b", 10),
            (r"\bcontinue\b|\bnext\b|\bsubmit\b", 2),
        ],
        success_patterns=[
            r"(membership|subscription|auto-?renew(al)?)[^.]{0,40}(has been|is now|was) (cancell?ed|turned off|ended|stopped)",
            r"cancell?ation (is )?(complete|confirmed)",
        ],
        choice_preferences=[(r"why|reason|leaving", NEUTRAL_CHOICE, r"")],
        fields=[FieldSpec("reason", r"\breason\b|why are you|tell us why|comments?|feedback")],
        consequences="Your subscription will stop renewing. Remaining paid time and any account benefits may end on the date shown by the service.",
    ),
    TaskType.REJECT_TRACKING: GoalProfile(
        task_type=TaskType.REJECT_TRACKING,
        title="Reject non-essential tracking",
        objective="Refuse all non-essential cookies and tracking while keeping strictly necessary ones.",
        goal_terms=[
            (r"\breject all\b|\breject (all )?(non-essential|optional|cookies|tracking)\b", 12),
            (r"\b(necessary|essential) (cookies )?only\b|\bonly (necessary|essential)\b", 10),
            (r"\b(decline|refuse|object to) (all|cookies|tracking)\b", 9),
            (r"\breject\b|\bdecline\b", 5),
        ],
        stage_terms=[
            (r"\b(manage|customi[sz]e|cookie|privacy) (settings|preferences|options|choices)\b", 6),
            (r"\b(more|show|other|advanced) options\b|\bsettings\b|\bpreferences\b|\bmanage\b|\bcustomi[sz]e\b", 4),
            (r"\bpurposes\b|\bvendors\b|\bpartners\b|\blegitimate interest\b", 2),
        ],
        submit_terms=[
            (r"\breject all\b|\b(necessary|essential) only\b", 12),
            (r"\b(save|confirm|apply) (my )?(choices|preferences|selection|settings)\b", 8),
            (r"\bsave\b|\bconfirm\b", 3),
        ],
        success_patterns=[
            r"(preferences|choices|settings|consent)[^.]{0,30}(have been|were|are) (saved|updated|recorded)",
            r"privacy choices saved",
        ],
        avoid_terms=[t for t in COMMON_AVOID if "allow" not in t[0]] + [
            (r"\baccept\b|\ballow( all)?\b|\bagree\b|\bok\b|\bcontinue( to site)?\b|\bgot it\b", -10),
        ],
        consequences="Non-essential cookies (analytics, advertising, social, partners) will be refused for this site. Strictly necessary cookies remain enabled. This can be changed later in the site's privacy settings.",
    ),
    TaskType.REQUEST_REFUND: GoalProfile(
        task_type=TaskType.REQUEST_REFUND,
        title="Request refund",
        objective="Submit a refund request for the specified order to the original payment method.",
        goal_terms=[
            (r"\b(request|start|begin|submit)( a)? (return or )?(refund|return)\b", 10),
            (r"\breturn(s)? (or|&|and) refund(s)?\b|\bstart a return\b", 7),
            (r"\brefund\b", 5),
            (r"\breturn\b", 2),
        ],
        stage_terms=[
            (r"\b(your|my) orders\b|\border history\b|\borders\b", 5),
            (r"\b(get )?help with (this |my )?order\b|\bproblem with (an |your |my )?order\b|\border (details|help)\b", 6),
            (r"\bview (order )?details\b", 3),
            (r"\bhelp( center)?\b|\bsupport\b|\bcontact\b|\baccount\b|\bfaqs?\b", 2.5),
        ],
        submit_terms=[
            (r"\bsubmit (my )?(refund|return)( request)?\b|\brequest (my )?refund\b", 10),
            (r"\bsubmit\b|\bsend (request)?\b", 4),
            (r"\bcontinue\b|\bnext\b", 2),
        ],
        success_patterns=[
            r"refund request[^.]{0,30}(has been |was )?(received|submitted|created)",
            r"(request|return) (number|reference|id)\b",
        ],
        fields=[
            FieldSpec("order_number", r"order (number|id|#|no)|\border\b", required_input=True),
            FieldSpec("reason", r"\breason\b", kind="choice"),
            FieldSpec("details", r"details|describe|description|comments?|additional information|tell us more"),
            FieldSpec("contact_email", r"e-?mail"),
        ],
        choice_preferences=[
            (r"refund (method|to|type|option)|how would you like|receive your refund|payment", r"original payment|card|bank|same payment", r"store credit|gift|voucher|points|exchange"),
            (r"survey|rate|satisf|how likely|experience|recommend", r"prefer not|neutral|no opinion|skip|other", r""),
        ],
        required_inputs=["order_number", "reason"],
        consequences="A refund request will be sent to the merchant for the order shown. The merchant decides eligibility and the amount; FairClick does not guarantee the outcome.",
    ),
    TaskType.DISPUTE_CHARGE: GoalProfile(
        task_type=TaskType.DISPUTE_CHARGE,
        title="Dispute a charge",
        objective="Prepare and submit a dispute for a specific charge, and prepare a summary for the user's bank.",
        goal_terms=[
            (r"\b(dispute|report)( a| this)? (charge|transaction|payment)\b|\bproblem with (a |this )?(charge|payment)\b", 10),
            (r"\bunrecogni[sz]ed (charge|payment)\b|\bwrong charge\b|\bdispute\b", 7),
        ],
        stage_terms=[
            (r"\bbilling\b|\bpayment(s)? (history|methods?)\b|\btransactions?\b|\bcharges?\b", 5),
            (r"\bsubscription( & | and )?billing\b", 5),
            (r"\bprofile\b|\baccount\b|\bsettings\b|\bhelp\b", 2),
        ],
        submit_terms=[
            (r"\bsubmit (my |this )?dispute\b|\bsend dispute\b|\bfile (a )?dispute\b", 10),
            (r"\bsubmit\b|\bsend\b", 4),
            (r"\bcontinue\b|\bnext\b", 2),
        ],
        success_patterns=[r"dispute[^.]{0,30}(has been |was )?(received|submitted|opened|logged)"],
        fields=[
            FieldSpec("transaction_id", r"transaction|charge|payment", kind="choice", required_input=True),
            FieldSpec("reason", r"\breason\b", kind="choice"),
            FieldSpec("details", r"details|describe|description|what happened|comments?|explain"),
        ],
        choice_preferences=[
            (r"resolution|outcome|would you like|instead", r"refund|reverse|original payment", r"free month|credit|voucher|instead"),
        ],
        required_inputs=["transaction_id", "reason"],
        consequences="A charge dispute will be opened with the merchant for the selected transaction. This does not by itself file a chargeback with your bank; the prepared summary can be used if you contact your bank.",
    ),
    TaskType.CLAIM_COMPENSATION: GoalProfile(
        task_type=TaskType.CLAIM_COMPENSATION,
        title="Claim compensation",
        objective="Submit a compensation claim for a disrupted trip, requesting payment rather than a voucher.",
        goal_terms=[
            (r"\b(submit|start|make|file)( a)? (compensation )?claim\b|\bclaim compensation\b|\bcompensation claim\b", 10),
            (r"\bcompensation\b", 6),
            (r"\bclaim\b", 3),
        ],
        stage_terms=[
            (r"\b(manage|my) (trips?|bookings?)\b|\btrips?\b|\bbookings?\b", 5),
            (r"\bdelays?( and | & |/)?(cancell?ations?)?\b|\bdisruption\b|\bflight problems?\b", 6),
            (r"\b(trip|booking) details\b|\bview (details|trip|booking)\b", 3),
            (r"\bhelp\b|\bsupport\b|\bcustomer service\b|\bfaqs?\b|frequently asked", 3),
        ],
        submit_terms=[
            (r"\bsubmit (my |the )?(compensation )?claim\b|\bsend (my )?claim\b", 10),
            (r"\bsubmit\b|\bsend\b", 4),
            (r"\bcontinue\b|\bnext\b", 2),
        ],
        success_patterns=[r"claim[^.]{0,40}(has been |was )?(received|submitted|registered|lodged)"],
        fields=[
            FieldSpec("booking_reference", r"booking (reference|ref|code|number)|\bpnr\b|confirmation code", required_input=True),
            FieldSpec("flight_number", r"flight (number|no)", required_input=True),
            FieldSpec("flight_date", r"(flight|travel|departure) date|date of (flight|travel)"),
            FieldSpec("delay_hours", r"delay|how late|arrival delay", kind="choice"),
            FieldSpec("passenger_name", r"(passenger|full|your) name|\bname\b", required_input=True),
            FieldSpec("contact_email", r"e-?mail", required_input=True),
            FieldSpec("details", r"details|describe|description|what happened|comments?"),
        ],
        choice_preferences=[
            (r"payment|paid|receive|compensation (method|type)|how would you like", r"bank|cash|transfer|original payment|money", r"voucher|credit|miles|points"),
        ],
        required_inputs=["booking_reference", "flight_number", "passenger_name", "contact_email"],
        consequences="A compensation claim will be sent to the travel provider. Eligibility and any amount are decided by the provider/regulator; FairClick does not guarantee compensation.",
    ),
}


# Inputs the user may provide per task, used by the API for validation and the UI.
TASK_INPUT_FIELDS: dict[str, list[dict[str, Any]]] = {
    "cancel_subscription": [
        {"key": "reason", "label": "Reason (optional)", "required": False, "max": 300},
    ],
    "reject_tracking": [],
    "request_refund": [
        {"key": "order_number", "label": "Order number", "required": True, "max": 40, "pattern": r"^[A-Za-z0-9-]{3,40}$"},
        {"key": "reason", "label": "Reason for refund", "required": True, "max": 120},
        {"key": "details", "label": "Details (optional)", "required": False, "max": 600},
    ],
    "dispute_charge": [
        {"key": "transaction_id", "label": "Transaction ID", "required": True, "max": 40, "pattern": r"^[A-Za-z0-9-]{3,40}$"},
        {"key": "reason", "label": "Reason for dispute", "required": True, "max": 120},
        {"key": "details", "label": "What happened (optional)", "required": False, "max": 600},
    ],
    "claim_compensation": [
        {"key": "booking_reference", "label": "Booking reference", "required": True, "max": 20, "pattern": r"^[A-Za-z0-9-]{3,20}$"},
        {"key": "flight_number", "label": "Flight number", "required": True, "max": 12, "pattern": r"^[A-Za-z0-9 ]{2,12}$"},
        {"key": "flight_date", "label": "Flight date (YYYY-MM-DD, optional)", "required": False, "max": 10, "pattern": r"^(\d{4}-\d{2}-\d{2})?$"},
        {"key": "delay_hours", "label": "Arrival delay in hours (optional)", "required": False, "max": 5, "pattern": r"^(\d{1,2}(\.\d)?)?$"},
        {"key": "passenger_name", "label": "Passenger name", "required": True, "max": 80},
        {"key": "contact_email", "label": "Contact email", "required": True, "max": 120, "pattern": r"^[^@\s]+@[^@\s]+\.[^@\s]+$"},
        {"key": "details", "label": "Details (optional)", "required": False, "max": 600},
    ],
}

RECOMMENDED_SITES: dict[str, list[str]] = {
    "cancel_subscription": ["streamplus", "fitlife"],
    "reject_tracking": ["cookieworld", "shopease"],
    "request_refund": ["shopease"],
    "dispute_charge": ["fitlife"],
    "claim_compensation": ["travelquick"],
}
