"""Seguidor de incidentes: abre, pasa a recuperación, reabre, cambia de nombre y cierra.

- Abre cuando el mismo tipo candidato se mantiene `k_open` instantes seguidos.
- Pasa a `recovering` cuando su causa desaparece (y baja un nivel la severidad); vuelve a `open`
  si la causa reaparece.
- Cambia de nombre hacia un tipo más grave (p. ej. `LINK_LOSS` → `HIJACK`) cuando el nuevo se
  mantiene `k_open` instantes, sin cerrar el incidente.
- Cierra tras `m_close` instantes sin candidato y con el dron en ruta.

Un incidente cambia de estado, no se sustituye: cada transición es una revisión más.
"""

from dataclasses import dataclass, replace

from poc_contracts.enums import IncidentChange, IncidentKind, IncidentState, Severity

from ..ids import IdAllocator

LOWER = {Severity.HIGH: Severity.MEDIUM, Severity.MEDIUM: Severity.LOW, Severity.LOW: Severity.LOW}
UNDETERMINED_QUIET_S = 20.0  # no se abre un «sin determinar» justo después de otra transición


@dataclass(frozen=True)
class Incident:
    incident_id: str
    revision: int
    kind: IncidentKind
    state: IncidentState
    severity: Severity
    opened_at: float
    change: IncidentChange
    as_of: float


class Tracker:
    def __init__(
        self,
        ids: IdAllocator,
        base_severity: dict[IncidentKind, Severity],
        rank: list[IncidentKind],
        k_open: int = 3,
        m_close: int = 10,
    ) -> None:
        self.ids = ids
        self.base = base_severity
        self.rank = rank
        self.k_open = k_open
        self.m_close = m_close
        self.reset()

    def reset(self) -> None:
        self.current: Incident | None = None
        self._pending: dict[IncidentKind, int] = {}
        self._normal_run = 0
        self._last_transition: float | None = None
        self.count = 0  # incidentes abiertos en la ejecución

    def _graver(self, a: IncidentKind, b: IncidentKind) -> bool:
        return self.rank.index(a) > self.rank.index(b)

    def _emit(self, incident: Incident, out: list[Incident]) -> None:
        self.current = None if incident.state == IncidentState.CLOSED else incident
        self._last_transition = incident.as_of
        out.append(incident)

    def _next(self, inc: Incident, t: float, change: IncidentChange, **fields: object) -> Incident:
        return replace(inc, revision=inc.revision + 1, change=change, as_of=t, **fields)  # type: ignore[arg-type]

    def revise(self, t: float, change: IncidentChange) -> Incident:
        """Otra revisión del incidente abierto sin cambiar su estado ni su nombre (las evidencias
        han cambiado)."""
        assert self.current is not None
        inc = self._next(self.current, t, change)
        self.current = inc
        self._last_transition = t
        return inc

    def step(self, t: float, candidate: IncidentKind | None, on_route: bool) -> list[Incident]:
        """Un instante: el tipo candidato de la tabla (o ninguno) y si el dron está en ruta.
        Devuelve las transiciones de este instante (normalmente ninguna)."""
        for kind in list(self._pending):
            if kind != candidate:
                del self._pending[kind]
        if candidate is not None:
            self._pending[candidate] = self._pending.get(candidate, 0) + 1
        out: list[Incident] = []
        inc = self.current
        if inc is None:
            if candidate is not None and self._pending[candidate] >= self.k_open:
                quiet = (
                    candidate == IncidentKind.UNDETERMINED
                    and self._last_transition is not None
                    and t - self._last_transition < UNDETERMINED_QUIET_S
                )
                if not quiet:
                    self.count += 1
                    opened = Incident(
                        self.ids.next("inc"), 1, candidate, IncidentState.OPEN,
                        self.base[candidate], t, IncidentChange.OPENED, t,
                    )  # fmt: skip
                    self._emit(opened, out)
            return out

        if (
            candidate is not None
            and candidate != inc.kind
            and self._pending[candidate] >= self.k_open
            and self._graver(candidate, inc.kind)
        ):
            inc = self._next(
                inc, t, IncidentChange.RENAMED, kind=candidate,
                severity=self.base[candidate], state=IncidentState.OPEN,
            )  # fmt: skip
            self._emit(inc, out)
        cause_on = candidate == inc.kind
        # un tipo más grave pendiente de confirmar no es «la causa ha desaparecido»
        graver_pending = (
            candidate is not None
            and candidate not in (IncidentKind.UNDETERMINED, inc.kind)
            and self._graver(candidate, inc.kind)
        )
        if inc.state == IncidentState.OPEN and not cause_on and not graver_pending:
            inc = self._next(
                inc, t, IncidentChange.STATE, state=IncidentState.RECOVERING,
                severity=LOWER[inc.severity],
            )  # fmt: skip
            self._emit(inc, out)
        elif inc.state == IncidentState.RECOVERING and cause_on:
            inc = self._next(
                inc, t, IncidentChange.STATE, state=IncidentState.OPEN, severity=self.base[inc.kind]
            )
            self._emit(inc, out)
        normal = candidate is None and on_route
        self._normal_run = self._normal_run + 1 if normal else 0
        if self._normal_run >= self.m_close:
            self._normal_run = 0
            self._emit(self._next(inc, t, IncidentChange.CLOSED, state=IncidentState.CLOSED), out)
        return out
