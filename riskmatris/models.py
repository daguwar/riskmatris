"""Pydantic request/response models."""

from pydantic import BaseModel


class CreateSessionRequest(BaseModel):
    title: str | None = "Riskanalys"
    threshold: int | None = 4
