"""Línea de texto de una detección, común a `detect_file` y al `__main__`."""

from poc_contracts.enums import EventType
from poc_contracts.envelope import EventDraft
from poc_contracts.payloads import DetectionCleared, DetectionRaised

_LABELS = {
    EventType.DETECTION_RAISED: "RAISED",
    EventType.DETECTION_UPDATED: "UPDATED",
    EventType.DETECTION_CLEARED: "CLEARED",
}


def format_time(sim_time: float) -> str:
    """`T+mm:ss` del instante simulado."""
    total = int(sim_time)
    return f"T+{total // 60:02d}:{total % 60:02d}"


class DetectionFormatter:
    """Da una línea por detección: `T+mm:ss  RAISED|UPDATED|CLEARED  regla  fuente|-  valor/umbral
    unidad  mensaje`. Recuerda la fuente de cada detección para ponerla también en el `CLEARED`,
    cuyo payload no la lleva."""

    def __init__(self) -> None:
        self._sources: dict[str, str] = {}

    def format(self, event: EventDraft) -> str:
        label = _LABELS[event.type]
        if event.type == EventType.DETECTION_CLEARED:
            cleared = DetectionCleared.model_validate(event.payload)
            source = self._sources.pop(cleared.detection_id, "-")
            rule = cleared.rule.value
            detail = f"max {cleared.max_value:g}"
            message = f"{cleared.detection_id} cerrada tras {cleared.duration_s:g} s"
        else:
            raised = DetectionRaised.model_validate(event.payload)
            source = raised.source.value if raised.source else "-"
            self._sources[raised.detection_id] = source
            rule = raised.rule.value
            detail = f"{raised.value:g}/{raised.threshold:g} {raised.unit}"
            message = f"{raised.detection_id} [{raised.severity.value}] {raised.message}"
        time = format_time(event.sim_time)
        return f"{time}  {label:<7}  {rule:<18}  {source:<7}  {detail:<14}  {message}"
