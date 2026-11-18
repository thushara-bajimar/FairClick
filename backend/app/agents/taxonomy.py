"""Dark-pattern taxonomy used by the Dark Pattern Detection Agent.

Categories follow the widely cited groupings from Gray et al. (2018),
Mathur et al. (2019) and the OECD (2022) dark-pattern reports.
"""
from __future__ import annotations

TAXONOMY: dict[str, dict[str, str]] = {
    "confirm_shaming": {
        "name": "Confirm-shaming",
        "description": "The option to decline is worded to guilt or shame the user into accepting.",
        "recommendation": "Ignore the emotional framing; choose the option that matches your goal.",
    },
    "hidden_information": {
        "name": "Hidden information",
        "description": "Material terms (charges, renewals, conditions) are de-emphasised or hidden from view.",
        "recommendation": "Read the fine print captured in the evidence before agreeing to anything.",
    },
    "obstruction": {
        "name": "Obstruction",
        "description": "The path to the user's goal is made harder than necessary (buried, low-visibility or multi-step).",
        "recommendation": "Keep the evidence; regulators treat 'easy to sign up, hard to cancel' as an unfair practice.",
    },
    "forced_action": {
        "name": "Forced action",
        "description": "The user must perform an unrelated action (survey, extra data, account) to continue.",
        "recommendation": "Provide only information that is genuinely required for your request.",
    },
    "interface_interference": {
        "name": "Interface interference",
        "description": "Visual design steers the user towards the option that benefits the business.",
        "recommendation": "Compare all options, not just the most prominent one.",
    },
    "nagging": {
        "name": "Nagging",
        "description": "The user is repeatedly interrupted with the same request or offer.",
        "recommendation": "Decline repeated prompts; your original decision stands.",
    },
    "fake_urgency": {
        "name": "Fake urgency",
        "description": "Countdowns or time pressure that are not genuine, intended to rush a decision.",
        "recommendation": "Take your time - the deadline is not real or not relevant to your request.",
    },
    "pre_selection": {
        "name": "Pre-selection",
        "description": "Options that benefit the business are selected by default.",
        "recommendation": "Untick anything you did not explicitly choose.",
    },
    "forced_continuity": {
        "name": "Forced continuity",
        "description": "A free or discounted period silently converts into a paid recurring charge.",
        "recommendation": "Note the renewal date and charge; cancel before it if you do not want it.",
    },
    "misdirection": {
        "name": "Misdirection",
        "description": "Labels or layout lead the user to a different outcome than the one they expect.",
        "recommendation": "Check where a button actually leads before clicking it.",
    },
}

SEVERITIES = ("low", "medium", "high")


def category_name(category: str) -> str:
    return TAXONOMY.get(category, {}).get("name", category)
