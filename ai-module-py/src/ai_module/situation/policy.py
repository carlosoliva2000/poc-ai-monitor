"""Política de incidentes (`policy.yaml`) y evidencias a partir de las filas de las tablas."""

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from poc_contracts.enums import IncidentKind, Severity

from ..decision.table import Rule

HERE = Path(__file__).resolve().parent
_COMPARISON = re.compile(r"^(<=|>=|<|>)\s*(-?\d+(?:\.\d+)?)$")


@dataclass(frozen=True)
class KindPolicy:
    name: str
    severity: Severity
    facets: list[str]
    checks: list[str]


@dataclass(frozen=True)
class Policy:
    rank: list[IncidentKind]
    kinds: dict[IncidentKind, KindPolicy]

    @property
    def base_severity(self) -> dict[IncidentKind, Severity]:
        return {kind: p.severity for kind, p in self.kinds.items()}


def load_policy(path: Path = HERE / "policy.yaml") -> Policy:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    kinds = {
        IncidentKind(name): KindPolicy(
            name=str(spec["name"]),
            severity=Severity(spec["severity"]),
            facets=[str(f) for f in spec["facets"]],
            checks=[str(c) for c in spec["checks"]],
        )
        for name, spec in raw["kinds"].items()
    }
    return Policy(rank=[IncidentKind(k) for k in raw["rank"]], kinds=kinds)


def _round(value: Any) -> Any:
    return round(value, 1) if isinstance(value, float) else value


def condition(feature: str, cell: Any, value: Any) -> dict[str, Any]:
    """Una celda de la tabla como condición legible: `>= 4` → op `>=`, umbral 4."""
    text = str(cell).strip() if not isinstance(cell, bool) else str(cell).lower()
    if match := _COMPARISON.match(text):
        op, threshold = match.group(1), float(match.group(2))
    elif text in ("true", "false"):
        op, threshold = "==", text == "true"
    elif text == "null":
        op, threshold = "==", None
    else:
        op, threshold = "==", ", ".join(part.strip().strip('"') for part in text.split(","))
    return {"feature": feature, "op": op, "threshold": threshold, "value": _round(value)}


def evidence_item(facet: str, rule: Rule, inputs: dict[str, Any]) -> dict[str, Any]:
    return {
        "facet": facet,
        "state": str(rule.then.get("state", rule.then.get("kind"))),
        "rule_id": rule.rule_id,
        "conditions": [condition(name, cell, inputs.get(name)) for name, cell in rule.when.items()],
    }
