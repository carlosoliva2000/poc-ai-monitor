"""Seguidor de incidentes: varios a la vez (uno por familia), con apertura, recuperación,
reapertura, cambio de nombre, escalado de la severidad y cierre.

- **Abre** cuando el mismo candidato de una familia se mantiene `k_open` instantes seguidos.
- **Cambia de nombre** hacia un tipo más grave de su familia (p. ej. `LINK_LOSS` → `HIJACK`) cuando
  ese candidato se mantiene `k_open` instantes, sin cerrar el incidente; un `UNDETERMINED` pasa a la
  causa que se confirma (de otra familia).
- **Recuperación:** en los tipos con `recovery`, cuando la causa desaparece pasa a `recovering` (y
  baja un nivel la severidad); cierra tras `m_close` instantes sin causa y con el dron en ruta. Si
  la causa reaparece no se reabre antes de `bounce_s` (el rebote al acabar la causa no son dos
  incidentes ni cuatro revisiones de estado); después, solo si se mantiene `k_open` instantes.
- Los demás tipos cierran tras `m_close` instantes sin causa.
- **Severidad:** base por tipo; sube un nivel si sigue abierto más de `escalate_after_s` sin
  mejorar o si empeora (el dron empieza a desviarse en un tipo con `escalate_on_deviation`, o una
  distancia se duplica: `escalate`); baja uno en recuperación. Una confianza `possible` no la sube.

Un incidente cambia de estado, no se sustituye: cada transición es una revisión más.
"""

from dataclasses import dataclass, replace

from poc_contracts.enums import IncidentChange, IncidentKind, IncidentState, Severity

from ..ids import IdAllocator
from .catalog import CONF, Candidate
from .policy import SEVERITIES, Policy


def raised(severity: Severity) -> Severity:
    return SEVERITIES[min(SEVERITIES.index(severity) + 1, len(SEVERITIES) - 1)]


def lowered(severity: Severity) -> Severity:
    return SEVERITIES[max(SEVERITIES.index(severity) - 1, 0)]


@dataclass(frozen=True)
class Incident:
    incident_id: str
    revision: int
    kind: IncidentKind
    subject: str | None
    family: str
    state: IncidentState
    severity: Severity
    confidence: str
    opened_at: float
    change: IncidentChange
    as_of: float
    since: float  # desde cuándo está en este estado
    severity_since: float  # desde cuándo tiene esta severidad


class Tracker:
    def __init__(self, ids: IdAllocator, policy: Policy) -> None:
        self.ids = ids
        self.policy = policy
        self.reset()

    def reset(self) -> None:
        self.current: dict[str, Incident] = {}  # por familia efectiva
        self.count = 0  # incidentes abiertos en la ejecución
        self.last_closed: dict[str, float] = {}
        self._pending: dict[str, tuple[tuple[IncidentKind, str | None], int]] = {}
        self._normal_run: dict[str, int] = {}
        self._worsened: set[str] = set()  # incidentes que ya subieron de nivel por empeorar
        self._aged: set[str] = set()  # y por llevar mucho tiempo abiertos

    # --- consulta --------------------------------------------------------------------------

    def open_families(self, t: float) -> frozenset[str]:
        """Familias con un incidente abierto o recuperando, o cerrado hace menos del rebote."""
        recent = {
            f
            for f, closed in self.last_closed.items()
            if t - closed < self.policy.defaults.bounce_s
        }
        return frozenset(set(self.current) | recent)

    # --- transiciones ----------------------------------------------------------------------

    def _next(self, inc: Incident, t: float, change: IncidentChange, **fields: object) -> Incident:
        return replace(inc, revision=inc.revision + 1, change=change, as_of=t, **fields)  # type: ignore[arg-type]

    def _emit(self, inc: Incident, out: list[Incident]) -> None:
        if inc.state == IncidentState.CLOSED:
            self.current.pop(inc.family, None)
            self.last_closed[inc.family] = inc.as_of
            self._normal_run.pop(inc.family, None)
        else:
            self.current[inc.family] = inc
        out.append(inc)

    def revise(self, family: str, t: float, change: IncidentChange) -> Incident:
        """Otra revisión sin cambiar estado, nombre ni severidad (las evidencias han cambiado)."""
        inc = self._next(self.current[family], t, change)
        self.current[family] = inc
        return inc

    def escalate(self, family: str, t: float) -> Incident | None:
        """Sube un nivel la severidad (el incidente empeora). `None` si ya está al máximo o la
        confianza es `possible`."""
        inc = self.current[family]
        if inc.state != IncidentState.OPEN or inc.confidence == "possible":
            return None
        if inc.incident_id in self._worsened or raised(inc.severity) == inc.severity:
            return None
        self._worsened.add(inc.incident_id)
        inc = self._next(
            inc, t, IncidentChange.SEVERITY, severity=raised(inc.severity), severity_since=t
        )
        self.current[family] = inc
        return inc

    def _update_pending(self, cands: dict[str, Candidate]) -> None:
        for family in list(self._pending):
            if family not in cands:
                del self._pending[family]
        for family, cand in cands.items():
            key = (cand.kind, cand.subject)
            previous = self._pending.get(family)
            self._pending[family] = (key, previous[1] + 1 if previous and previous[0] == key else 1)

    def _ready(self, family: str, cand: Candidate) -> bool:
        key, count = self._pending[family]
        return key == (cand.kind, cand.subject) and count >= self.policy.k_open(cand.kind)

    def step(
        self,
        t: float,
        cands: dict[str, Candidate],
        on_route: bool,
        deviated: bool,
        hold: set[str] | frozenset[str] = frozenset(),
    ) -> list[Incident]:
        """Un instante: el candidato de cada familia, si el dron está en ruta, si está desviado y
        qué familias no se pueden leer ahora (se quedan como están). Devuelve las transiciones de
        este instante (normalmente ninguna)."""
        self._update_pending(cands)
        out: list[Incident] = []
        handled: set[str] = set()
        self._undetermined_becomes(t, cands, out, handled)
        becoming = "undetermined" in self.current and any(
            c.kind in self.policy.undetermined_becomes and f not in self.current
            for f, c in cands.items()
        )  # una causa se confirma: «sin determinar» no ha desaparecido, va a cambiar de nombre
        for family in sorted(set(cands) | set(self.current)):
            if family in handled or family in hold or (becoming and family == "undetermined"):
                continue
            cand = cands.get(family)
            inc = self.current.get(family)
            if inc is None:
                assert cand is not None
                if self._ready(family, cand):
                    self._open(t, cand, out)
                continue
            self._follow(t, inc, cand, on_route, deviated, out)
        return out

    def _open(self, t: float, cand: Candidate, out: list[Incident]) -> None:
        self.count += 1
        severity = self.policy.base_severity(cand.kind, cand.subject)
        inc = Incident(
            self.ids.next("inc"), 1, cand.kind, cand.subject, cand.family, IncidentState.OPEN,
            severity, cand.confidence, t, IncidentChange.OPENED, t, t, t,
        )  # fmt: skip
        self._emit(inc, out)

    def _undetermined_becomes(
        self, t: float, cands: dict[str, Candidate], out: list[Incident], handled: set[str]
    ) -> None:
        inc = self.current.get("undetermined")
        if inc is None:
            return
        for family, cand in sorted(cands.items()):
            becomes = cand.kind in self.policy.undetermined_becomes
            if becomes and family not in self.current and self._ready(family, cand):
                renamed = self._next(
                    inc, t, IncidentChange.RENAMED, kind=cand.kind, subject=cand.subject,
                    family=family, state=IncidentState.OPEN, confidence=cand.confidence,
                    severity=self.policy.base_severity(cand.kind, cand.subject),
                    since=t, severity_since=t,
                )  # fmt: skip
                self.current.pop("undetermined")
                self._emit(renamed, out)
                handled.add(family)
                return

    def _follow(
        self, t: float, inc: Incident, cand: Candidate | None, on_route: bool, deviated: bool,
        out: list[Incident],
    ) -> None:  # fmt: skip
        family = inc.family
        if (
            cand is not None
            and cand.kind != inc.kind
            and self.policy.family_of[cand.kind] == self.policy.family_of[inc.kind]
            and self.policy.rank(cand.kind) > self.policy.rank(inc.kind)
            and self._ready(family, cand)
        ):
            inc = self._next(
                inc, t, IncidentChange.RENAMED, kind=cand.kind, subject=cand.subject,
                state=IncidentState.OPEN, confidence=cand.confidence,
                severity=self.policy.base_severity(cand.kind, cand.subject),
                since=t, severity_since=t,
            )  # fmt: skip
            self._emit(inc, out)
        cause_on = cand is not None
        if cause_on and cand.kind == inc.kind and cand.confidence != inc.confidence:
            inc = replace(inc, confidence=cand.confidence)  # se publica con la siguiente revisión
            self.current[family] = inc
        kind_policy = self.policy.kinds[inc.kind]
        if inc.state == IncidentState.OPEN:
            if cause_on:
                self._normal_run[family] = 0
                self._maybe_escalate(t, inc, deviated, out)
            elif kind_policy.recovery:
                inc = self._next(
                    inc, t, IncidentChange.STATE, state=IncidentState.RECOVERING,
                    severity=lowered(inc.severity), since=t, severity_since=t,
                )  # fmt: skip
                self._emit(inc, out)
                self._normal_run[family] = 1 if on_route else 0
            else:
                self._normal_run[family] = self._normal_run.get(family, 0) + 1
        elif cause_on:  # recuperando y la causa reaparece
            self._normal_run[family] = 0
            ready = cand is not None and self._ready(family, cand)
            if ready and t - inc.since >= self.policy.defaults.bounce_s:
                severity = self.policy.base_severity(inc.kind, inc.subject)
                inc = self._next(
                    inc, t, IncidentChange.STATE, state=IncidentState.OPEN, severity=severity,
                    since=t, severity_since=t,
                )  # fmt: skip
                self._emit(inc, out)
        elif on_route:
            self._normal_run[family] = self._normal_run.get(family, 0) + 1
        else:
            self._normal_run[family] = 0
        quiet = not cause_on or inc.state == IncidentState.RECOVERING
        if quiet and self._normal_run.get(family, 0) >= self.policy.m_close(inc.kind):
            self._emit(self._next(inc, t, IncidentChange.CLOSED, state=IncidentState.CLOSED), out)

    def _maybe_escalate(self, t: float, inc: Incident, deviated: bool, out: list[Incident]) -> None:
        if inc.confidence == "possible":
            return
        aged = t - inc.severity_since >= self.policy.defaults.escalate_after_s
        if aged and inc.incident_id not in self._aged:
            self._aged.add(inc.incident_id)
            if raised(inc.severity) != inc.severity:
                self._emit(
                    self._next(inc, t, IncidentChange.SEVERITY, severity=raised(inc.severity),
                               severity_since=t),
                    out,
                )  # fmt: skip
            return
        kind = self.policy.kinds[inc.kind]
        if deviated and kind.escalate_on_deviation and inc.incident_id not in self._worsened:
            self._worsened.add(inc.incident_id)
            if raised(inc.severity) != inc.severity:
                self._emit(
                    self._next(inc, t, IncidentChange.SEVERITY, severity=raised(inc.severity),
                               severity_since=t),
                    out,
                )  # fmt: skip


__all__ = ["CONF", "Incident", "Tracker", "lowered", "raised"]
