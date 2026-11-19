from dataclasses import dataclass, field

from ..config import SERVICES
from ..spaces import ROOT_CAUSES, Action

SEVERITY_SCORE = {"low": 0.25, "medium": 0.5, "high": 0.75, "critical": 1.0}

RCA_SCHEMA = {
    "type": "object",
    "properties": {
        "root_cause_category": {"type": "string", "enum": ROOT_CAUSES},
        "severity": {"type": "string", "enum": list(SEVERITY_SCORE)},
        "affected_component": {"type": "string", "enum": SERVICES + ["unknown"]},
        "confidence": {"type": "number"},
        "evidence": {"type": "array", "items": {"type": "string"}},
        "explanation": {"type": "string"},
        "suggested_action": {"type": "string", "enum": [a.name for a in Action]},
    },
    "required": ["root_cause_category", "severity", "affected_component", "confidence",
                 "evidence", "explanation", "suggested_action"],
    "additionalProperties": False,
}


@dataclass
class RCAResult:
    category: str = "unknown"
    severity: str = "medium"
    affected_component: str = "unknown"
    confidence: float = 0.0
    explanation: str = ""
    evidence: list = field(default_factory=list)
    suggested_action: str = "NO_OP"
    source: str = "none"

    @classmethod
    def unknown(cls, reason: str = "", confidence: float = 0.0) -> "RCAResult":
        return cls(category="unknown", confidence=confidence, explanation=reason, source="fallback")

    @classmethod
    def from_json(cls, data: dict, source: str, conf_threshold: float) -> "RCAResult":
        result = cls(category=data["root_cause_category"], severity=data["severity"],
                     affected_component=data["affected_component"],
                     confidence=min(max(float(data["confidence"]), 0.0), 1.0),
                     explanation=data["explanation"], evidence=list(data.get("evidence", [])),
                     suggested_action=data.get("suggested_action", "NO_OP"), source=source)
        if result.confidence < conf_threshold:
            result.category = "unknown"          
        return result

    def as_features(self) -> dict:
        feats = {f"rc_{c}": float(self.category == c) for c in ROOT_CAUSES}
        feats["severity"] = SEVERITY_SCORE.get(self.severity, 0.5) if self.category != "unknown" else 0.0
        feats["confidence"] = float(self.confidence)
        return feats