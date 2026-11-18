"""Backend for the five *simulated* websites (mounted under /sites).

These endpoints play the role of the companies' servers. They only write to the
separate sim_sites.db and never contact any real service.
"""
from __future__ import annotations

import json
import secrets
from urllib.parse import urlencode

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse

from .. import database as db
from ..security import is_sensitive_field

router = APIRouter(prefix="/sites")

# (site, kind) -> (reference prefix, page to redirect to)
SUBMISSIONS = {
    ("streamplus", "cancel"): ("SP", "cancel/done.html"),
    ("streamplus", "accept_offer"): ("SPO", "offer-accepted.html"),
    ("shopease", "refund"): ("SE", "refund-done.html"),
    ("shopease", "consent"): ("SEC", "cookies-saved.html"),
    ("shopease", "subscribe"): ("SEN", "index.html"),
    ("cookieworld", "consent"): ("CW", "consent-saved.html"),
    ("fitlife", "cancel"): ("FL", "cancel-done.html"),
    ("fitlife", "accept_offer"): ("FLO", "offer-accepted.html"),
    ("fitlife", "dispute"): ("DSP", "dispute-done.html"),
    ("travelquick", "claim"): ("CLM", "claim-done.html"),
    ("travelquick", "accept_voucher"): ("TQV", "voucher-accepted.html"),
}

COOKIE_CATEGORIES = ("analytics", "advertising", "social", "personalisation", "partners")


@router.post("/{site}/submit/{kind}")
async def submit(site: str, kind: str, request: Request) -> RedirectResponse:
    if (site, kind) not in SUBMISSIONS:
        raise HTTPException(404, "Unknown form")
    form = await request.form()
    payload = {k: str(v)[:500] for k, v in form.multi_items() if not is_sensitive_field(k)}
    prefix, page = SUBMISSIONS[(site, kind)]
    reference = f"{prefix}-{secrets.token_hex(3).upper()}"
    params: dict[str, str] = {"ref": reference}

    if kind == "consent":
        choice = payload.get("choice", "save")
        for cat in COOKIE_CATEGORIES:
            if choice == "accept_all":
                state = "1"
            elif choice == "reject_all":
                state = "0"
            else:
                state = "1" if payload.get(cat) == "on" else "0"
            params[cat] = state
        payload["resolved"] = json.dumps(params)
    if site == "shopease" and kind == "refund":
        if not payload.get("order_number"):
            raise HTTPException(400, "Order number is required")
        params["order"] = payload["order_number"][:40]
        params["method"] = payload.get("refund_method", "")
    if site == "travelquick" and kind == "claim":
        params["payout"] = payload.get("payout", "")
    if site == "fitlife" and kind == "dispute":
        params["txn"] = payload.get("transaction", "")[:40]
        params["resolution"] = payload.get("resolution", "")

    with db.sim_db() as conn:
        conn.execute("INSERT INTO sim_submissions(site, kind, reference, payload_json, created_at) VALUES (?,?,?,?,?)",
                     (site, kind, reference, json.dumps(payload), db.utcnow()))
    return RedirectResponse(f"/sites/{site}/{page}?{urlencode(params)}", status_code=303)
