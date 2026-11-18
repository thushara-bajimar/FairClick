"""Pydantic request models with input validation."""
from __future__ import annotations

import re
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

from .agents.goals import TASK_INPUT_FIELDS
from .security import SITE_IDS, clean_text, is_sensitive_field


class TaskCreate(BaseModel):
    task_type: str
    site_id: str
    inputs: dict[str, str] = Field(default_factory=dict)
    start: bool = True

    @field_validator("task_type")
    @classmethod
    def _task_type(cls, value: str) -> str:
        if value not in TASK_INPUT_FIELDS:
            raise ValueError(f"task_type must be one of {sorted(TASK_INPUT_FIELDS)}")
        return value

    @field_validator("site_id")
    @classmethod
    def _site(cls, value: str) -> str:
        if value not in SITE_IDS:
            raise ValueError(f"site_id must be one of {list(SITE_IDS)}")
        return value

    @model_validator(mode="after")
    def _inputs(self) -> "TaskCreate":
        spec = {f["key"]: f for f in TASK_INPUT_FIELDS[self.task_type]}
        cleaned: dict[str, str] = {}
        for key, raw in self.inputs.items():
            if key not in spec:
                raise ValueError(f"Unexpected input '{key}' for {self.task_type}")
            if is_sensitive_field(key):
                raise ValueError("Sensitive credentials must never be provided to FairClick")
            value = clean_text(raw, spec[key]["max"])
            if value and spec[key].get("pattern") and not re.fullmatch(spec[key]["pattern"], value):
                raise ValueError(f"Invalid format for '{spec[key]['label']}'")
            if value:
                cleaned[key] = value
        missing = [f["label"] for f in spec.values() if f["required"] and not cleaned.get(f["key"])]
        if missing:
            raise ValueError("Missing required input: " + ", ".join(missing))
        # Reject anything that looks like a card number in free text.
        for value in cleaned.values():
            if re.search(r"\b(?:\d[ -]?){13,19}\b", value):
                raise ValueError("Inputs must not contain card numbers")
        self.inputs = cleaned
        return self


class ApprovalDecision(BaseModel):
    approved: bool
    comment: str = Field(default="", max_length=500)
    decided_by: str = Field(default="user", max_length=60)

    @field_validator("comment", "decided_by")
    @classmethod
    def _clean(cls, value: str) -> str:
        return clean_text(value, 500)


class SettingsUpdate(BaseModel):
    display_name: Optional[str] = Field(default=None, max_length=60)
    require_approval_for_consent: Optional[bool] = None
    capture_screenshots: Optional[bool] = None
    headless_browser: Optional[bool] = None
    step_delay_ms: Optional[int] = Field(default=None, ge=0, le=3000)
    retain_history_days: Optional[int] = Field(default=None, ge=1, le=3650)
    store_page_text: Optional[bool] = None

    def changes(self) -> dict[str, Any]:
        data = self.model_dump(exclude_none=True)
        if "display_name" in data:
            data["display_name"] = clean_text(data["display_name"], 60)
        return data
