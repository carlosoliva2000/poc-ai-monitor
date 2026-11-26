"""Del estado de las facetas a los incidentes: vista enmascarada → catálogo → seguidor.

Lo usan el monitor en directo y la evaluación fuera de línea (con el estado de la verdad en lugar
del estimado), así que los incidentes de la verdad y los del monitor salen del mismo catálogo y del
mismo seguidor.
"""

from poc_contracts.enums import IncidentKind

from ..ids import IdAllocator
from .catalog import FAILSAFE_MODES, NOT_OBSERVABLE, TELEMETRY, Candidate, View, candidates, mask
from .policy import Policy
from .tracker import Incident, Tracker


class IncidentEngine:
    def __init__(self, ids: IdAllocator, policy: Policy, tracker: Tracker | None = None) -> None:
        self.ids = ids
        self.policy = policy
        self.tracker = tracker or Tracker(ids, policy)
        self.reset()

    def reset(self) -> None:
        self.tracker.reset()
        self._failsafe_explained = False
        self._previous_mode = "mission"
        self.view = View(states={})
        self.candidates: dict[str, Candidate] = {}
        self.held: set[str] = set()  # familias que no se pueden leer ahora

    def step(
        self, t: float, states: dict[str, str], conf: dict[str, str] | None = None
    ) -> list[Incident]:
        """Un instante: el estado de cada faceta (y la confianza de su fila, si la hay)."""
        conf = conf or {}
        masked = mask(states)
        mode = masked.get("drone.mode", "mission")
        families = self.tracker.open_families(t)
        if mode in FAILSAFE_MODES and self._previous_mode not in FAILSAFE_MODES:
            # el failsafe ya lo explica otro incidente (enlace) o el enlace está caído ahora
            lost = states.get("link.availability") == "lost"
            self._failsafe_explained = "control" in families or lost
        elif mode not in FAILSAFE_MODES:
            self._failsafe_explained = False
        self._previous_mode = mode
        self.view = View(masked, conf, families, self._failsafe_explained)
        self.candidates = candidates(self.view, self.policy)
        situation = masked.get("drone.situation", "on_route")
        self.held = self._unobservable()
        return self.tracker.step(
            t, self.candidates, situation == "on_route", situation == "deviated", self.held
        )

    def _unobservable(self) -> set[str]:
        """Familias con un incidente cuyas facetas no se pueden leer ahora (`?`): ni siguen ni
        «la causa ha desaparecido», se quedan como están (p. ej. la batería sin telemetría
        mientras el enlace está caído)."""
        held: set[str] = set()
        for family, inc in self.tracker.current.items():
            facets = self.policy.decided_facets(inc.kind, inc.subject)
            if facets and all(self.view.state(f) == NOT_OBSERVABLE for f in facets):
                held.add(family)
            elif (
                inc.kind == IncidentKind.SOURCE_SILENT
                and inc.subject in TELEMETRY
                and "control" in self.view.open_families
            ):
                held.add(family)  # tras volver el enlace, la telemetría tarda en llegar
        return held


def cause_kind(cause: str) -> IncidentKind | None:
    """El tipo de incidente que corresponde a una causa de desviación."""
    return {
        "foreign_control": IncidentKind.HIJACK,
        "spoofed_position": IncidentKind.GPS_SPOOFING,
        "dead_reckoning": IncidentKind.DEAD_RECKONING,
        "wind": IncidentKind.WIND,
    }.get(cause)
