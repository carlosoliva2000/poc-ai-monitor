"""Política de incidentes (`policy.yaml`) y evidencias a partir de las filas de las tablas."""

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from poc_contracts.enums import IncidentKind, Severity

from ..decision.table import Rule

HERE = Path(__file__).resolve().parent
_COMPARISON = re.compile(r"^(<=|>=|<|>)\s*(-?\d+(?:\.\d+)?)$")
_RANGE = re.compile(r"^\(\s*(-?\d+(?:\.\d+)?)\s*\.\.\s*(-?\d+(?:\.\d+)?)\s*\]$")
SEVERITIES = [Severity.LOW, Severity.MEDIUM, Severity.HIGH]


@dataclass(frozen=True)
class SubjectPolicy:
    name: str
    severity: Severity | None
    facet: str | None


@dataclass(frozen=True)
class KindPolicy:
    name: str
    severity: Severity
    recovery: bool
    escalate_on_deviation: bool
    facets: list[str]
    decided_by: dict[str, list[str]]
    checks: list[str]
    subjects: dict[str, SubjectPolicy]
    k_open: int | None
    m_close: int | None


@dataclass(frozen=True)
class Defaults:
    k_open: int
    m_close: int
    bounce_s: float
    escalate_after_s: float
    drift_factor: float


@dataclass(frozen=True)
class Policy:
    defaults: Defaults
    families: dict[str, list[IncidentKind]]
    kinds: dict[IncidentKind, KindPolicy]
    undetermined_becomes: list[IncidentKind]
    explains_deviation: list[str]
    family_of: dict[IncidentKind, str] = field(default_factory=dict)

    def k_open(self, kind: IncidentKind) -> int:
        return self.kinds[kind].k_open or self.defaults.k_open

    def m_close(self, kind: IncidentKind) -> int:
        return self.kinds[kind].m_close or self.defaults.m_close

    def base_severity(self, kind: IncidentKind, subject: str | None = None) -> Severity:
        sub = self.kinds[kind].subjects.get(subject or "")
        return sub.severity if sub and sub.severity else self.kinds[kind].severity

    def name(self, kind: IncidentKind, subject: str | None = None) -> str:
        policy = self.kinds[kind]
        sub = policy.subjects.get(subject or "")
        if sub:
            return sub.name
        return policy.name.format(subject=subject or "")

    def facets(self, kind: IncidentKind, subject: str | None = None) -> list[str]:
        sub = self.kinds[kind].subjects.get(subject or "")
        facets = [f.format(subject=subject or "") for f in self.kinds[kind].facets]
        return facets if not sub or not sub.facet else [sub.facet, *facets[1:]]

    def decided_facets(self, kind: IncidentKind, subject: str | None = None) -> list[str]:
        """Las facetas que deciden un tipo (para una fuente, solo la suya)."""
        sub = self.kinds[kind].subjects.get(subject or "")
        if sub and sub.facet:
            return [sub.facet]
        return list(self.kinds[kind].decided_by)

    def rank(self, kind: IncidentKind) -> int:
        return self.families[self.family_of[kind]].index(kind)


def _subjects(raw: dict[str, Any]) -> dict[str, SubjectPolicy]:
    return {
        key: SubjectPolicy(
            name=str(spec["name"]),
            severity=Severity(spec["severity"]) if "severity" in spec else None,
            facet=spec.get("facet"),
        )
        for key, spec in raw.items()
    }


def load_policy(path: Path = HERE / "policy.yaml") -> Policy:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    families = {f: [IncidentKind(k) for k in kinds] for f, kinds in raw["families"].items()}
    kinds = {
        IncidentKind(name): KindPolicy(
            name=str(spec["name"]),
            severity=Severity(spec["severity"]),
            recovery=bool(spec.get("recovery", False)),
            escalate_on_deviation=bool(spec.get("escalate_on_deviation", False)),
            facets=[str(f) for f in spec["facets"]],
            decided_by={f: [str(s) for s in states] for f, states in spec["decided_by"].items()},
            checks=[str(c) for c in spec["checks"]],
            subjects=_subjects(spec.get("subjects", {})),
            k_open=spec.get("k_open"),
            m_close=spec.get("m_close"),
        )
        for name, spec in raw["kinds"].items()
    }
    family_of = {kind: family for family, members in families.items() for kind in members}
    missing = set(IncidentKind) - set(kinds)
    if missing or set(family_of) != set(kinds):
        raise ValueError(f"policy.yaml: kinds without policy or family: {sorted(missing)}")
    defaults = Defaults(**{k: raw["defaults"][k] for k in Defaults.__dataclass_fields__})
    return Policy(
        defaults=defaults,
        families=families,
        kinds=kinds,
        undetermined_becomes=[IncidentKind(k) for k in raw["undetermined_becomes"]],
        explains_deviation=list(raw["explains_deviation"]),
        family_of=family_of,
    )


def _round(value: Any) -> Any:
    return round(value, 1) if isinstance(value, float) else value


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
        low, high = (round(float(match.group(i)), 4) for i in (1, 2))
        return [one(">", low), one("<=", high)]
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
