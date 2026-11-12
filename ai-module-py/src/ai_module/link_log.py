"""Registro del enlace de mando que lleva el módulo (código, sin LLM): cuál es el controlador de
la misión (el primero visto en la ejecución, como el detector) y cuándo cambia el controlador.

Lo usa el informe (Fase 15.1) para dar la hora a la que el enlace volvió al controlador de la
misión: la del primer `LinkStatus` con ese controlador, no la del cierre de la `LINK_ANOMALY` (que
llega unos segundos después porque el detector espera a estar seguro).
"""

from dataclasses import dataclass, field

from poc_contracts.envelope import EventDraft


@dataclass(frozen=True)
class LinkChange:
    """Un `LinkStatus` cuyo controlador no es el del evento anterior."""

    sim_time: float
    event_id: str
    controller_id: str


@dataclass
class LinkLog:
    mission_controller: str | None = None
    changes: list[LinkChange] = field(default_factory=list)
    _last: str | None = None

    def observe(self, event: EventDraft) -> None:
        """Anota un `LinkStatus`: el primero fija el controlador de la misión y cada cambio de
        controlador se guarda."""
        controller = str(event.payload.get("controller_id"))
        if self.mission_controller is None:
            self.mission_controller = controller
        if controller != self._last:
            self.changes.append(LinkChange(event.sim_time, event.event_id, controller))
            self._last = controller

    def back_after(self, since: float) -> LinkChange | None:
        """El primer `LinkStatus` posterior a `since` con el controlador de la misión, tras haber
        estado otro en el enlace (`None` si no hubo cambio o aún no ha vuelto)."""
        away = False
        for change in self.changes:
            if change.sim_time < since:
                away = change.controller_id != self.mission_controller
                continue
            if change.controller_id != self.mission_controller:
                away = True
            elif away:
                return change
        return None

    def reset(self) -> None:
        self.mission_controller = self._last = None
        self.changes.clear()
