"""Evaluación por incidente del monitor de situación sobre las variantes de la E7b.

- `compute_trace`: el estado de cada faceta por segundo que estima el monitor (las tablas
  aprendidas congeladas sobre los eventos de una variante), guardado en caché.
- `truth_incidents`: los incidentes «de verdad», con **el mismo catálogo y el mismo seguidor** pero
  alimentados con el estado verdadero de las facetas (`states.jsonl`), con k = m = 1.
- `monitor_incidents`: los incidentes del monitor con unos k y m.
- `score`: detectados por tipo, retraso, falsos por hora y por gravedad, parpadeos.
"""

import pickle
import statistics
import sys
from collections import defaultdict
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools" / "training"))

from features import read_states, variant_assets  # noqa: E402

from ai_module.ids import IdAllocator  # noqa: E402
from ai_module.situation.engine import IncidentEngine  # noqa: E402
from ai_module.situation.features import FeatureExtractor  # noqa: E402
from ai_module.situation.monitor import SituationMonitor  # noqa: E402
from ai_module.situation.policy import Policy, load_policy  # noqa: E402
from ai_module.situation.replay import is_world, read_events  # noqa: E402
from ai_module.situation.tracker import Incident  # noqa: E402
from poc_contracts.enums import IncidentChange, IncidentState  # noqa: E402

ATTACK = ("HIJACK", "GPS_SPOOFING")  # una falsa alarma de ataque pesa más que una avería
ATTACK_WEIGHT = 3.0
TRUTH_MERGE_S = 20.0  # los incidentes de verdad de una familia y tipo a menos de esto, uno solo
SHORT_TRUTH_S = 10.0  # un incidente de verdad más corto es un transitorio: no se exige verlo
SLACK_BEFORE_S = 10.0  # un incidente del monitor que abre antes de esto no es de ese de verdad
SLACK_AFTER_S = 60.0  # ni el que sigue abierto hasta después de esto (cierre más recuperación)
FLICKER_S = 30.0  # mismo tipo y familia reabierto a menos de esto = parpadeo
Trace = list[tuple[float, dict[str, str], dict[str, str]]]


# --- trazas ------------------------------------------------------------------------------------


def variant_monitor(folder: Path) -> SituationMonitor:
    """El monitor con las tablas congeladas y el extractor creado con los activos de la variante:
    las ventanas de frescura, la caducidad del radar y las líneas base se calculan al construir el
    extractor, así que asignarle `assets` después no basta (con el GPS a 3 s, cada tercer segundo
    quedaba «sin dato fresco»)."""
    monitor = SituationMonitor(tables="learned")
    monitor.features = FeatureExtractor(variant_assets(folder))
    return monitor


def compute_trace(folder: Path) -> Trace:
    """Lo que estima el monitor cada segundo: estado de cada faceta y confianza de su fila."""
    monitor = variant_monitor(folder)
    trace: Trace = []

    def take(rows: list[Any]) -> None:
        for row in rows:
            snap = monitor.facets.evaluate(row)
            trace.append((row.t, dict(snap.states), dict(snap.confidence)))

    for event in read_events(folder / "events.jsonl.gz"):
        if is_world(event):
            take(monitor.features.push(event))
    take(monitor.features.flush())
    return trace


def cached_trace(folder: Path, cache: Path) -> Trace:
    path = cache / f"{folder.name}.pkl"
    if path.exists():
        return pickle.loads(path.read_bytes())
    trace = compute_trace(folder)
    cache.mkdir(parents=True, exist_ok=True)
    path.write_bytes(pickle.dumps(trace))
    return trace


def truth_trace(folder: Path) -> Trace:
    states = read_states(folder / "states.jsonl.gz")
    return [(float(t), dict(facets), {}) for t, facets in sorted(states.items())]


# --- incidentes ----------------------------------------------------------------------------------


@dataclass
class Record:
    """Un incidente a lo largo de su vida (de la verdad o del monitor)."""

    incident_id: str
    families: set[str]
    kinds: dict[str, float]  # tipo → primer instante en que lo tuvo
    final_kind: str
    opened: float
    closed: float
    reopened: int = 0  # veces que volvió de `recovering` a `open`
    kind_changes: list[tuple[float, str]] = field(default_factory=list)

    @property
    def attack(self) -> bool:
        return any(k in ATTACK for k in self.kinds)


def records(policy: Policy, trace: Trace, end: float) -> list[Record]:
    """Pasa una traza por el motor de incidentes y reúne la vida de cada incidente."""
    engine = IncidentEngine(IdAllocator(), policy)
    live: dict[str, Record] = {}
    done: list[Record] = []
    for t, states, conf in trace:
        for inc in engine.step(t, states, conf):
            _record(inc, live, done, t)
    for rec in live.values():
        rec.closed = end
        done.append(rec)
    return done


def _record(inc: Incident, live: dict[str, Record], done: list[Record], t: float) -> None:
    rec = live.get(inc.incident_id)
    if rec is None:
        rec = live[inc.incident_id] = Record(
            inc.incident_id, {inc.family}, {inc.kind.value: t}, inc.kind.value, t, t
        )
    rec.families.add(inc.family)
    rec.kinds.setdefault(inc.kind.value, t)
    rec.final_kind = inc.kind.value
    if inc.change == IncidentChange.RENAMED:
        rec.kind_changes.append((t, inc.kind.value))
    if inc.change == IncidentChange.STATE and inc.state == IncidentState.OPEN:
        rec.reopened += 1
    if inc.state == IncidentState.CLOSED:
        rec.closed = t
        done.append(live.pop(inc.incident_id))


def truth_policy(policy: Policy) -> Policy:
    """Sin retardos: el incidente de verdad es lo que dice la verdad, al instante."""
    kinds = {k: replace(p, k_open=None, m_close=None) for k, p in policy.kinds.items()}
    defaults = replace(policy.defaults, k_open=1, m_close=1, bounce_s=0.0)
    return replace(policy, defaults=defaults, kinds=kinds)


def monitor_policy(policy: Policy, k: int, m: int) -> Policy:
    return replace(policy, defaults=replace(policy.defaults, k_open=k, m_close=m))


def truth_incidents(folder: Path, policy: Policy | None = None) -> list[Record]:
    policy = truth_policy(policy or load_policy())
    trace = truth_trace(folder)
    found = records(policy, trace, trace[-1][0] if trace else 0.0)
    return merge(found)


def merge(found: list[Record]) -> list[Record]:
    """Une los incidentes de la verdad de una misma familia separados por menos de `TRUTH_MERGE_S`
    (la calidad por valor físico parpadea cerca del umbral)."""
    out: list[Record] = []
    for rec in sorted(found, key=lambda r: r.opened):
        for prev in reversed(out):
            if prev.families & rec.families and rec.opened - prev.closed <= TRUTH_MERGE_S:
                prev.closed = max(prev.closed, rec.closed)
                for kind, t in rec.kinds.items():
                    prev.kinds.setdefault(kind, t)
                prev.final_kind = rec.final_kind
                break
        else:
            out.append(rec)
    return out


# --- puntuación ----------------------------------------------------------------------------------


@dataclass
class Variant:
    """Lo necesario de una variante para puntuar: sus incidentes de verdad y los del monitor."""

    name: str
    hours: float
    truth: list[Record]
    monitor: list[Record]


def overlaps(m: Record, t: Record) -> bool:
    return bool(m.families & t.families) and (
        m.opened <= t.closed + SLACK_AFTER_S and m.closed >= t.opened - SLACK_BEFORE_S
    )


def score(variants: list[Variant]) -> dict[str, Any]:
    """Métricas por incidente del conjunto de variantes."""
    hours = sum(v.hours for v in variants)
    per_kind: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"truth": 0, "detected": 0, "kind_ok": 0, "delay_open": [], "delay_kind": []}
    )
    false_other = false_attack = 0
    false_by_kind: dict[str, int] = defaultdict(int)
    flicker = reopened = 0
    truth_total = detected_total = short_truth = 0
    for v in variants:
        matched_monitor: set[str] = set()
        for t in v.truth:
            if t.closed - t.opened < SHORT_TRUTH_S:
                short_truth += 1
                continue
            truth_total += 1
            hits = [m for m in v.monitor if overlaps(m, t)]
            matched_monitor.update(m.incident_id for m in hits)
            detected_total += bool(hits)
            # una fila por cada nombre que tuvo el de verdad (p. ej. batería baja → crítica)
            for kind, since in t.kinds.items():
                row = per_kind[kind]
                row["truth"] += 1
                if not hits:
                    continue
                row["detected"] += 1
                row["delay_open"].append(min(m.opened for m in hits) - t.opened)
                reached = [m.kinds[kind] for m in hits if kind in m.kinds]
                if reached:
                    row["kind_ok"] += 1
                    row["delay_kind"].append(min(reached) - since)
        for m in v.monitor:
            mine = [t for t in v.truth if overlaps(m, t)]
            wrong_attack = [
                k for k in m.kinds if k in ATTACK and not any(k in t.kinds for t in mine)
            ]
            if wrong_attack:  # una alarma de ataque que la verdad no tiene
                false_attack += 1
                false_by_kind[wrong_attack[0]] += 1
            elif not mine:
                false_other += 1
                false_by_kind[m.final_kind] += 1
            reopened += m.reopened
        flicker += _flicker(v.monitor)
    return {
        "hours": hours,
        "truth_incidents": truth_total,
        "detected_incidents": detected_total,
        "short_truth_incidents": short_truth,
        "false_attack_per_h": false_attack / hours,
        "false_other_per_h": false_other / hours,
        "false_weighted_per_h": (ATTACK_WEIGHT * false_attack + false_other) / hours,
        "false_by_kind": dict(sorted(false_by_kind.items())),
        "flicker_pct": 100.0 * (flicker + reopened) / max(truth_total, 1),
        "per_kind": {k: _summary(r) for k, r in sorted(per_kind.items())},
    }


def _flicker(monitor: list[Record]) -> int:
    """Incidentes del mismo tipo y familia que se vuelven a abrir a menos de `FLICKER_S`."""
    count = 0
    ordered = sorted(monitor, key=lambda r: r.opened)
    for i, rec in enumerate(ordered):
        for prev in ordered[:i]:
            same = prev.families & rec.families and prev.final_kind == rec.final_kind
            if same and 0 <= rec.opened - prev.closed <= FLICKER_S:
                count += 1
                break
    return count


def _quantile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, round(q * (len(ordered) - 1)))]


def _summary(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "truth": row["truth"], "detected": row["detected"], "kind_ok": row["kind_ok"],
        "delay_open_median": statistics.median(row["delay_open"]) if row["delay_open"] else None,
        "delay_open_p90": _quantile(row["delay_open"], 0.9),
        "delay_kind_median": statistics.median(row["delay_kind"]) if row["delay_kind"] else None,
    }  # fmt: skip
