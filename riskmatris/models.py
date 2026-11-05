"""Pydantic request/response models and typed dicts for internal state.

The session/risk structures are stored as plain dicts (they are serialized to
SQLite as JSON), so full Pydantic models would require conversion at every
boundary. Instead, ``Session``/``Risk``/``Vote`` are TypedDicts: zero runtime
cost, but the keys are documented and type-checked.
"""

from typing import TypedDict

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Typed dicts for the internal session/risk state
# ---------------------------------------------------------------------------


class Vote(TypedDict):
    probability: int
    consequence: int
    updated_at: float


class Risk(TypedDict, total=False):
    number: int
    label: str
    votes: dict[str, Vote]
    revealed: bool
    locked: bool
    final_probability: int | None
    final_consequence: int | None


class Session(TypedDict, total=False):
    session_id: str
    admin_token: str
    title: str
    threshold: int
    created_at: float
    updated_at: float
    active_risk_number: int
    risks: list[Risk]


# ---------------------------------------------------------------------------
# HTTP request/response models
# ---------------------------------------------------------------------------


class CreateSessionRequest(BaseModel):
    title: str | None = "Riskanalys"
    threshold: int | None = Field(default=4, ge=1, le=50)


class HealthResponse(BaseModel):
    status: str
    active_sessions: int
    db_path: str


class CreateSessionResponse(BaseModel):
    session_id: str
    admin_token: str
    title: str
    threshold: int
    lan_ip: str


class WsTicketResponse(BaseModel):
    ticket: str
    expires_in: int
