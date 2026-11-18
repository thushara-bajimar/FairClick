"""Security helpers: navigation allowlist, input sanitisation, injection screening."""
from __future__ import annotations

import html
import re
from urllib.parse import urlparse

from .config import settings

SITE_IDS = ("streamplus", "shopease", "cookieworld", "fitlife", "travelquick")

# Patterns that indicate a website is trying to instruct an AI agent.
INJECTION_PATTERNS: list[re.Pattern[str]] = [
    re.compile(p, re.IGNORECASE)
    for p in (
        r"ignore (all |any |your )?(previous|prior|above|earlier|original) (instructions|prompts|rules|directions)",
        r"disregard (all |any |your |the )?(previous |prior )?(instructions|rules|guidelines|task)",
        r"forget (your|all|the) (instructions|rules|task|goal)",
        r"you are now (an?|the) ",
        r"new (system )?instructions?\s*:",
        r"system prompt",
        r"reveal (the |all |any |your )?(stored |saved |private )?(user |personal |customer )?(information|data|details|credentials|passwords?)",
        r"(send|share|output|print|enter|type) (the |all |your )?(stored |saved )?(user'?s? )?(password|credentials|card number|cvv|api key|personal data)",
        r"\b(ai|llm) (agents?|assistants?|bots?)\s*[:,-]",
        r"note to (ai|automated|llm) (agents?|assistants?)",
    )
]

# Field labels that must never be auto-filled, whatever the website asks for.
SENSITIVE_FIELD_PATTERN = re.compile(
    r"pass(word|code)|\bpin\b|cvv|cvc|security code|card number|credit card|iban|account number|"
    r"routing|sort code|social security|\bssn\b|api key|secret",
    re.IGNORECASE,
)

MAX_INPUT_LENGTH = 2000


def is_allowed_url(url: str) -> bool:
    """Only the locally hosted simulation sites may be opened by the browser agent."""
    if url.startswith(("about:blank", "data:")):
        return True
    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    base = urlparse(settings.base_url)
    if parsed.scheme not in ("http", "https"):
        return False
    if parsed.hostname not in ("127.0.0.1", "localhost") or parsed.hostname != base.hostname:
        return False
    if (parsed.port or 80) != (base.port or 80):
        return False
    # The agent's browser may only load the simulation sites - not FairClick's
    # own API (so a malicious page cannot e.g. approve its own request).
    return parsed.path.startswith("/sites/")


def site_start_url(site_id: str) -> str:
    if site_id not in SITE_IDS:
        raise ValueError(f"Unknown simulated site: {site_id}")
    return f"{settings.base_url}/sites/{site_id}/index.html"


_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def sanitize_text(value: str, max_length: int = MAX_INPUT_LENGTH) -> str:
    """Strip control characters and HTML-escape user supplied text."""
    value = _CONTROL_CHARS.sub("", str(value)).strip()
    return html.escape(value[:max_length], quote=True)


def clean_text(value: str, max_length: int = MAX_INPUT_LENGTH) -> str:
    """Strip control characters without escaping (for values typed into forms)."""
    return _CONTROL_CHARS.sub("", str(value)).strip()[:max_length]


def find_injections(text: str) -> list[str]:
    """Return the sentences of `text` that look like instructions aimed at an AI agent."""
    hits: list[str] = []
    if not text:
        return hits
    for sentence in re.split(r"(?<=[.!?])\s+|\n+", text):
        sentence = sentence.strip()
        if sentence and any(p.search(sentence) for p in INJECTION_PATTERNS):
            hits.append(sentence[:300])
    return hits


def is_sensitive_field(label: str) -> bool:
    return bool(SENSITIVE_FIELD_PATTERN.search(label or ""))
