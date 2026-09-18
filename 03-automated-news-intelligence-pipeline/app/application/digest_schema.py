"""Pydantic models for OpenAI Structured Outputs digest generation."""

from math import isfinite
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

from app.domain.enums import DigestTag

CandidateId = Annotated[
    str,
    StringConstraints(pattern=r"^c_\d{2}$", min_length=4, max_length=5),
]
SummaryText = Annotated[str, StringConstraints(min_length=80, max_length=280)]
SelectionReason = Annotated[str, StringConstraints(min_length=1, max_length=300)]
RelevanceScore = Annotated[float, Field(ge=0.0, le=1.0)]


class DigestModelItem(BaseModel):
    """One model-selected digest entry identified by an opaque candidate id."""

    model_config = ConfigDict(extra="forbid")

    candidate_id: CandidateId
    summary: SummaryText
    tag: DigestTag
    relevance_score: RelevanceScore
    selection_reason: SelectionReason

    @field_validator("relevance_score")
    @classmethod
    def require_finite_score(cls, value: float) -> float:
        if not isfinite(value):
            raise ValueError("relevance_score must be finite")
        return value


class DigestModelOutput(BaseModel):
    """Strict structured digest payload returned by the model."""

    model_config = ConfigDict(extra="forbid")

    digest_title: Annotated[str, StringConstraints(min_length=1, max_length=200)]
    items: Annotated[list[DigestModelItem], Field(min_length=1, max_length=7)]

    @field_validator("items")
    @classmethod
    def require_unique_candidate_ids(
        cls,
        value: list[DigestModelItem],
    ) -> list[DigestModelItem]:
        ids = [item.candidate_id for item in value]
        if len(ids) != len(set(ids)):
            raise ValueError("candidate_id values must be unique")
        return value
