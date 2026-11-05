"""Session and risk domain logic."""

import secrets
from typing import Any

import riskmatris.config as config
import riskmatris.db as db
from riskmatris.models import Risk, Session
from riskmatris.utils import get_risk_level, round_half_up


def generate_session_id(sessions: dict[str, Session] | None = None) -> str:
    """Generates a readable code (default 8 chars = 40 bits, without confusable
    characters like 0/O, 1/I). Length is configurable via SESSION_CODE_LENGTH
    (6 chars gave only ~30 bits of entropy)."""
    alphabet = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"
    length = getattr(config, "SESSION_CODE_LENGTH", 8)
    active_sessions = sessions if sessions is not None else db.SESSIONS
    while True:
        code = "".join(secrets.choice(alphabet) for _ in range(length))
        if code not in active_sessions:
            return code


def create_new_risk(number: int, label: str = "") -> Risk:
    return {
        "number": number,
        "label": label.strip(),
        "votes": {},  # client_id -> {"probability": int, "consequence": int, "updated_at": float}
        "revealed": False,
        "locked": False,
        "final_probability": None,
        "final_consequence": None,
    }


def get_session_threshold(session: Session) -> int:
    """Returns the session's configured vote threshold.

    The threshold is the exact number of votes needed to auto-reveal a risk's
    result. It is deliberately never adjusted to the number of currently
    connected participants: the system cannot know how many participants are
    expected, only the meeting leader can. Revealing early would leak partial
    results to the room before everyone has voted.
    """
    return max(1, int(session.get("threshold", 4)))


def compute_risk_stats(risk: Risk, threshold: int) -> dict[str, Any]:
    """Computes statistics for a risk without side effects (pure function).

    Also returns ``threshold_reached`` so the caller can update
    ``risk['revealed']`` explicitly when needed.
    """
    votes_list = list(risk["votes"].values())
    vote_count = len(votes_list)

    # Threshold is reached if votes exist and the count >= threshold (and the risk is not already revealed)
    threshold_reached = vote_count > 0 and vote_count >= threshold and not risk["revealed"]

    is_revealed = bool(risk["revealed"] or risk["locked"])

    avg_prob: float | None = None
    avg_cons: float | None = None
    suggested_prob: int | None = None
    suggested_cons: int | None = None
    cell_counts: dict[str, int] = {}

    if vote_count > 0:
        avg_prob = round(sum(v["probability"] for v in votes_list) / vote_count, 2)
        avg_cons = round(sum(v["consequence"] for v in votes_list) / vote_count, 2)
        suggested_prob = round_half_up(avg_prob)
        suggested_cons = round_half_up(avg_cons)

        for v in votes_list:
            key = f"{v['probability']}_{v['consequence']}"
            cell_counts[key] = cell_counts.get(key, 0) + 1

    final_prob = risk["final_probability"] or suggested_prob
    final_cons = risk["final_consequence"] or suggested_cons
    final_score = (final_prob * final_cons) if (final_prob and final_cons) else None
    risk_meta = get_risk_level(final_score) if final_score else None

    return {
        "number": risk["number"],
        "label": risk["label"],
        "vote_count": vote_count,
        "revealed": is_revealed,
        "locked": risk["locked"],
        "threshold_reached": threshold_reached,
        "avg_probability": avg_prob if is_revealed else None,
        "avg_consequence": avg_cons if is_revealed else None,
        "suggested_probability": suggested_prob if is_revealed else None,
        "suggested_consequence": suggested_cons if is_revealed else None,
        "final_probability": risk["final_probability"] if is_revealed else None,
        "final_consequence": risk["final_consequence"] if is_revealed else None,
        "effective_probability": final_prob if is_revealed else None,
        "effective_consequence": final_cons if is_revealed else None,
        "score": final_score if is_revealed else None,
        "level": risk_meta["level"] if (is_revealed and risk_meta) else None,
        "color": risk_meta["color"] if (is_revealed and risk_meta) else None,
        "cell_counts": cell_counts if is_revealed else {},
    }
