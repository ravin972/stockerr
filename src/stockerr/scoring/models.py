"""Scoring data structures."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


def clamp(x: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, x))


@dataclass
class SubScore:
    """One dimension (fundamental / technical / sentiment) scored 0-100."""

    name: str
    available: bool
    score: float = 0.0                      # 0-100 (meaningful only if available)
    detail: dict = field(default_factory=dict)   # per-check breakdown
    note: str = ""

    @classmethod
    def unavailable(cls, name: str, note: str) -> "SubScore":
        return cls(name=name, available=False, score=0.0, note=note)


@dataclass
class StockScore:
    symbol: str
    confidence: Optional[float]   # 0-100, or None if nothing could be scored
    fundamental: SubScore
    technical: SubScore
    sentiment: SubScore
    notes: str = ""
    rationale: str = ""           # plain-English "why" behind the score

    def to_row(self) -> dict:
        def s(sub: SubScore):
            return round(sub.score, 1) if sub.available else None
        return {
            "symbol": self.symbol,
            "confidence": round(self.confidence, 1) if self.confidence is not None else None,
            "fundamental": s(self.fundamental),
            "technical": s(self.technical),
            "sentiment": s(self.sentiment),
            "why": self.rationale,
            "notes": self.notes,
        }
