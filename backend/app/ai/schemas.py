"""Strict Pydantic v2 schemas for every LLM response — spec §16.

`extra="forbid"` on all four models is deliberate: §16 requires rejection when
schema fields are absent, and forbidding unknown fields closes the matching hole
where a model smuggles an extra `amount` or `recommendation` key past us.

These types describe *shape only*. Whether the content is truthful is decided by
`validators.py` against backend state — a schema-valid response that claims the
wrong number is still rejected.
"""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field

_STRICT = ConfigDict(extra="forbid", str_strip_whitespace=True)


class MerchantResolution(BaseModel):
    """§16 MerchantResolution. Produced only for the 70-89 confidence band (§14)."""

    model_config = _STRICT

    normalized_merchant: str = Field(min_length=1, max_length=120)
    category: str = Field(min_length=1, max_length=60)
    explanation: str = Field(min_length=1, max_length=600)
    confidence: float = Field(ge=0.0, le=1.0)
    evidence_tokens: List[str] = Field(default_factory=list, max_length=20)


class InsightExplanation(BaseModel):
    """§16 InsightExplanation. Wording only — every number must already exist."""

    model_config = _STRICT

    insight_type: str = Field(min_length=1, max_length=60)
    title: str = Field(min_length=1, max_length=160)
    explanation: str = Field(min_length=1, max_length=1200)
    evidence_transaction_ids: List[str] = Field(default_factory=list, max_length=50)
    suggested_action: Optional[str] = Field(default=None, max_length=400)
    confidence: float = Field(ge=0.0, le=1.0)


class ActionDraft(BaseModel):
    """§16 ActionDraft — a message the *user* may choose to send. Never sent by us."""

    model_config = _STRICT

    action_type: str = Field(min_length=1, max_length=40)
    merchant: str = Field(min_length=1, max_length=120)
    subject: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=3000)
    facts_used: List[str] = Field(default_factory=list, max_length=30)
    unsupported_claims: List[str] = Field(default_factory=list, max_length=30)


class VerificationResult(BaseModel):
    """§16 VerificationResult — second-model check on a high-impact finding (§14)."""

    model_config = _STRICT

    supported: bool
    contradictions: List[str] = Field(default_factory=list, max_length=30)
    unsupported_values: List[str] = Field(default_factory=list, max_length=30)
    corrected_text: Optional[str] = Field(default=None, max_length=1200)
    confidence: float = Field(ge=0.0, le=1.0)


#: Every schema the router may request, by name — used for logging and routing.
SCHEMAS = {
    "MerchantResolution": MerchantResolution,
    "InsightExplanation": InsightExplanation,
    "ActionDraft": ActionDraft,
    "VerificationResult": VerificationResult,
}
