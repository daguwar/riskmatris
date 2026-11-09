"""Session snapshot export/import (issue #15).

A snapshot is a JSON file with the full session state (risks, labels, locked
placements, optionally votes) that can be imported into a NEW session – e.g.
to resume a workshop next week after the original session expired.
"""

import time
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from riskmatris.config import (
    MAX_CLIENT_ID_LENGTH,
    MAX_LABEL_LENGTH,
    MAX_RISKS_PER_SESSION,
    MAX_VOTES_PER_RISK,
)
from riskmatris.session import create_new_risk
from riskmatris.utils import sanitize_user_text

SNAPSHOT_FORMAT = "riskmatris-snapshot"
SNAPSHOT_VERSION = 1
MAX_RISKS_PER_SNAPSHOT = MAX_RISKS_PER_SESSION


class SnapshotVote(BaseModel):
    probability: int = Field(ge=1, le=4)
    consequence: int = Field(ge=1, le=4)


class SnapshotRisk(BaseModel):
    number: int = Field(ge=1, le=9999)
    label: str = ""
    revealed: bool = False
    locked: bool = False
    final_probability: int | None = Field(default=None, ge=1, le=4)
    final_consequence: int | None = Field(default=None, ge=1, le=4)
    votes: dict[str, SnapshotVote] = Field(default_factory=dict)


class SnapshotFile(BaseModel):
    """The on-disk snapshot format. Strict: unknown fields are rejected and
    ``format``/``version`` must match exactly."""

    model_config = {"extra": "forbid"}

    format: Literal[SNAPSHOT_FORMAT]
    version: Literal[SNAPSHOT_VERSION]
    title: str = ""
    threshold: int = Field(default=4, ge=1, le=50)
    exported_at: str = ""
    risks: list[SnapshotRisk] = Field(default_factory=list, max_length=MAX_RISKS_PER_SNAPSHOT)


def build_snapshot(session: dict[str, Any], include_votes: bool = True) -> dict[str, Any]:
    """Builds the exportable snapshot dict for a session (never contains the admin token).

    Raw votes (with client IDs) are only included when ``include_votes`` is set –
    the export endpoint passes the admin flag, so unauthenticated requests can
    never read individual votes (audit 2026-11 SEC-01).
    """
    risks = []
    for r in session.get("risks", []):
        votes = (
            {
                sanitize_user_text(cid, MAX_CLIENT_ID_LENGTH): {
                    "probability": v["probability"],
                    "consequence": v["consequence"],
                }
                for cid, v in list(r.get("votes", {}).items())[:MAX_VOTES_PER_RISK]
            }
            if include_votes
            else {}
        )
        risks.append(
            {
                "number": r["number"],
                "label": r.get("label", ""),
                "revealed": bool(r.get("revealed")),
                "locked": bool(r.get("locked")),
                "final_probability": r.get("final_probability"),
                "final_consequence": r.get("final_consequence"),
                "votes": votes,
            }
        )
    return {
        "format": SNAPSHOT_FORMAT,
        "version": SNAPSHOT_VERSION,
        "title": session.get("title", ""),
        "threshold": int(session.get("threshold", 4)),
        "exported_at": datetime.now(UTC).isoformat(),
        "risks": risks,
    }


def risks_from_snapshot(snap: SnapshotFile, include_votes: bool) -> list[dict[str, Any]]:
    """Builds risk dicts from a validated snapshot. Labels/client ids are sanitized."""
    risks = []
    for sr in snap.risks:
        risk = create_new_risk(sr.number, sanitize_user_text(sr.label, MAX_LABEL_LENGTH))
        risk["locked"] = sr.locked
        risk["revealed"] = sr.revealed or sr.locked
        risk["final_probability"] = sr.final_probability
        risk["final_consequence"] = sr.final_consequence
        if include_votes:
            for cid, vote in list(sr.votes.items())[:MAX_VOTES_PER_RISK]:
                risk["votes"][sanitize_user_text(cid, MAX_CLIENT_ID_LENGTH)] = {
                    "probability": vote.probability,
                    "consequence": vote.consequence,
                    "updated_at": time.time(),
                }
        risks.append(risk)
    return risks
