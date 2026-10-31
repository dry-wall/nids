"""Advisory brief v1 (Appendix A.2). Phase 1: citations may be empty - no retrieval in the generator yet."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

FAMILIES = ["DoS", "DDoS", "PortScan", "Brute Force", "Web Attack", "Bot", "Infiltration", "Unknown"]

# Appendix A.3 starter mapping. The generator may only emit technique IDs from this allow-list.
TECHNIQUES_OF_FAMILY = {
    "DoS": ["T1499"],
    "DDoS": ["T1498"],
    "PortScan": ["T1046"],
    "Brute Force": ["T1110"],
    "Web Attack": ["T1190"],
    "Bot": ["T1071"],
    "Infiltration": [],
    "Unknown": [],
}
ALLOWED_TECHNIQUES = sorted({t for ts in TECHNIQUES_OF_FAMILY.values() for t in ts})


class Deviation(BaseModel):
    feature: str
    value: float | None
    z: float


class Hypothesis(BaseModel):
    family: Literal["DoS", "DDoS", "PortScan", "Brute Force", "Web Attack", "Bot", "Infiltration", "Unknown"]
    technique_ids: list[str] = Field(default_factory=list)
    confidence_note: str
    reasoning: str = ""

    @field_validator("technique_ids")
    @classmethod
    def only_allowed(cls, v):
        return [t for t in v if t in ALLOWED_TECHNIQUES]


class Action(BaseModel):
    step: str
    citations: list[str] = Field(default_factory=list)


class Brief(BaseModel):
    record_id: str
    summary: str
    why_flagged: list[Deviation]
    hypothesis: Hypothesis
    impact: str
    actions: list[Action] = Field(min_length=1, max_length=8)
    citations: list[dict] = Field(default_factory=list)
    limitations: str


# What the LLM is asked to produce (record_id / why_flagged are filled from the detector's own facts,
# never from the model, so the numbers in a brief always match the detector exactly).
LLM_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "hypothesis": {
            "type": "object",
            "properties": {
                "family": {"type": "string", "enum": FAMILIES},
                "technique_ids": {"type": "array", "items": {"type": "string", "enum": ALLOWED_TECHNIQUES}},
                "reasoning": {"type": "string"},
                "confidence_note": {"type": "string"},
            },
            "required": ["family", "technique_ids", "reasoning", "confidence_note"],
        },
        "impact": {"type": "string"},
        "actions": {"type": "array", "items": {"type": "string"}, "minItems": 3, "maxItems": 6},
        "limitations": {"type": "string"},
    },
    "required": ["summary", "hypothesis", "impact", "actions", "limitations"],
}
