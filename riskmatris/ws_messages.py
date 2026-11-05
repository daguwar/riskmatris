"""Pydantic models for WebSocket messages.

The dispatch loop in ``routes/ws.py`` validates every incoming message against
the model registered for its action *before* the handler runs, giving automatic
type/range validation and clearer error messages. The handlers themselves keep
their defensive ``_safe_int`` checks (they are also called directly by tests).

All fields except ``action`` are optional: the handlers apply their own
defaults (e.g. ``lock_risk`` falls back to the suggested cell), so validation
here only rejects values that are present but invalid.
"""

from typing import Literal

from pydantic import BaseModel, Field, ValidationError


class VoteMessage(BaseModel):
    action: Literal["vote"] = "vote"
    probability: int = Field(ge=1, le=4)
    consequence: int = Field(ge=1, le=4)


class RevealNowMessage(BaseModel):
    action: Literal["reveal_now"] = "reveal_now"


class SetLabelMessage(BaseModel):
    action: Literal["set_label"] = "set_label"
    label: str = ""
    number: int | None = Field(default=None, ge=1, le=9999)


class SetTitleMessage(BaseModel):
    action: Literal["set_title"] = "set_title"
    title: str = ""


class SetThresholdMessage(BaseModel):
    action: Literal["set_threshold"] = "set_threshold"
    threshold: int | None = Field(default=None, ge=1, le=50)


class LockRiskMessage(BaseModel):
    action: Literal["lock_risk"] = "lock_risk"
    probability: int | None = Field(default=None, ge=1, le=4)
    consequence: int | None = Field(default=None, ge=1, le=4)


class UnlockRiskMessage(BaseModel):
    action: Literal["unlock_risk"] = "unlock_risk"


class SetFinalCellMessage(BaseModel):
    action: Literal["set_final_cell"] = "set_final_cell"
    probability: int = Field(ge=1, le=4)
    consequence: int = Field(ge=1, le=4)
    lock: bool = False


class NextRiskMessage(BaseModel):
    action: Literal["next_risk"] = "next_risk"
    label: str = ""
    auto_lock: bool = True


class SelectRiskMessage(BaseModel):
    action: Literal["select_risk"] = "select_risk"
    number: int | None = Field(default=None, ge=1, le=9999)


class ResetVotesMessage(BaseModel):
    action: Literal["reset_votes"] = "reset_votes"


class DeleteRiskMessage(BaseModel):
    action: Literal["delete_risk"] = "delete_risk"
    number: int | None = Field(default=None, ge=1, le=9999)


class SetQrVisibleMessage(BaseModel):
    """Admin toggles the large QR overlay in the session's presentation views."""

    action: Literal["set_qr_visible"] = "set_qr_visible"
    visible: bool = True


WS_ACTION_MODELS: dict[str, type[BaseModel]] = {
    model.model_fields["action"].default: model
    for model in (
        VoteMessage,
        RevealNowMessage,
        SetLabelMessage,
        SetTitleMessage,
        SetThresholdMessage,
        LockRiskMessage,
        UnlockRiskMessage,
        SetFinalCellMessage,
        NextRiskMessage,
        SelectRiskMessage,
        ResetVotesMessage,
        DeleteRiskMessage,
        SetQrVisibleMessage,
    )
}


def parse_ws_message(action: str, raw: dict) -> BaseModel | None:
    """Validates a raw WS message against the model for its action.

    Raises ``pydantic.ValidationError`` if the message does not match.
    Returns ``None`` for unknown actions (the dispatcher rejects those
    separately with a permission/unknown-action error).
    """
    model_cls = WS_ACTION_MODELS.get(action)
    if model_cls is None:
        return None
    return model_cls.model_validate(raw)


def format_validation_error(exc: ValidationError) -> str:
    """Renders a ValidationError as a compact, human-readable string."""
    parts = []
    for err in exc.errors():
        loc = ".".join(str(x) for x in err["loc"] if x != "action")
        parts.append(f"{loc or 'meddelande'}: {err['msg']}")
    return "Ogiltigt meddelande – " + "; ".join(parts)
