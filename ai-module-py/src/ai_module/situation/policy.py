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


_RANGE = re.compile(r"^\(\s*(-?\d+(?:\.\d+)?)\s*\.\.\s*(-?\d+(?:\.\d+)?)\s*\]$")


def conditions(feature: str, cell: Any, value: Any) -> list[dict[str, Any]]:
    """Una celda de la tabla como condiciones legibles: `>= 4` → op `>=`, umbral 4.

    Las tablas aprendidas añaden `, null` («o sin dato») a una comparación, `(a..b]` para un rango
    y `not(null)`: el rango son dos condiciones (`>` a y `<=` b); el «o sin dato» no se pinta (el
    valor `null` ya lo dice), y `not(null)` es `!= null`."""
    text = str(cell).strip() if not isinstance(cell, bool) else str(cell).lower()
    shown = _round(value) if not isinstance(value, float) else round(value, 4)

    def one(op: str, threshold: Any) -> dict[str, Any]:
        return {"feature": feature, "op": op, "threshold": threshold, "value": shown}

    if match := _COMPARISON.match(text):
        return [one(match.group(1), round(float(match.group(2)), 4))]
    if match := _RANGE.match(text):
        return [
            one(">", round(float(match.group(1)), 4)),
            one("<=", round(float(match.group(2)), 4)),
        ]
    if text == "not(null)":
        return [one("!=", None)]
    parts = [part.strip() for part in text.split(",")]
    if len(parts) > 1 and parts[-1] == "null" and parts[0] != "null":
        inner = ", ".join(parts[:-1])
        if _COMPARISON.match(inner) or _RANGE.match(inner):
            return conditions(feature, inner, value)
    if text in ("true", "false"):
        return [one("==", text == "true")]
    if text == "null":
        return [one("==", None)]
    return [one("==", ", ".join(part.strip('"') for part in parts))]


def evidence_item(facet: str, rule: Rule, inputs: dict[str, Any]) -> dict[str, Any]:
    return {
        "facet": facet,
        "state": str(rule.then.get("state", rule.then.get("kind"))),
        "rule_id": rule.rule_id,
        "conditions": [
            c for name, cell in rule.when.items() for c in conditions(name, cell, inputs.get(name))
        ],
    }
