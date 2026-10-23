"""Estado del monitor (opción B de memoria): puro, sin E/S y probado.

Lleva las alertas (con sus cadenas de `supersedes`), a qué alerta pertenece cada detección, qué
detecciones siguen abiertas y las últimas decisiones. Se alimenta con los eventos del bus
(`apply`) y también con los que publica el propio módulo; es idempotente por `event_id`, así que
el eco de un evento propio no se cuenta dos veces.

Una **cadena** de alertas (cada una sustituye a la anterior con `supersedes`) es un solo
episodio: la alerta «en vigor» es la última, y las detecciones de toda la cadena pertenecen a ella.
"""

from collections import deque
from dataclasses import dataclass, field

from poc_contracts.enums import AlertStatus, EventType
from poc_contracts.envelope import EventDraft
from poc_contracts.payloads import (
    AlertClosed,
    AnomalyDetected,
    DetectionAcknowledged,
    DetectionCleared,
    DetectionRaised,
)

from .outbox import format_t

CHECK_LABELS = {
    "gps_alert_recent": "recent GPS alert",
    "gps_radar_disagreed": "GPS and radar disagree",
    "wind_notable": "notable wind",
    "wind_with_drift": "drift in favour of the wind",
    "link_checked": "link checked",
    "link_anomalous": "link anomalous",
}
"""Cómo se llama cada comprobación de `AnomalyDetected.checks` en los textos para personas."""


@dataclass
class DetectionRecord:
    detection_id: str
    rule: str
    source: str | None
    severity: str
    since: float
    open: bool = True
    closed_at: float | None = None
    alert_id: str | None = None
    """Alerta a la que pertenece (puede estar sustituida: se sigue la cadena hasta la vigente)."""
    opened_severity: str = ""
    message: str = ""
    """Texto del detector al abrirse, para el informe."""
    value: float = 0.0
    threshold: float = 0.0
    unit: str = ""
    updates: list[tuple[float, str, float, str]] = field(default_factory=list)
    """Cada `DetectionUpdated`: `(sim_time, severidad, valor, mensaje)`."""
    max_value: float | None = None
    """Valor máximo que alcanzó (lo da el `DetectionCleared`)."""


@dataclass
class AlertRecord:
    alert_id: str
    cause: str
    severity: str
    confidence: float
    summary: str
    sim_time: float
    detection_ids: set[str] = field(default_factory=set)
    supersedes: str | None = None
    superseded_by: str | None = None
    status: AlertStatus = AlertStatus.OPEN
    fallback: bool = False
    closed_at: float | None = None
    explanation: str = ""
    recommendation: str = ""
    evidence_ids: list[str] = field(default_factory=list)
    checks: dict | None = None


class MonitorState:
    def __init__(self, last_decisions: int = 3) -> None:
        self.last_decisions = last_decisions
        self.reset()

    def reset(self) -> None:
        self.alerts: dict[str, AlertRecord] = {}
        self.detections: dict[str, DetectionRecord] = {}
        self.decisions: deque[str] = deque(maxlen=self.last_decisions)
        self._seen: set[str] = set()
        self.chains_published = 0

    # --- Alimentación ---------------------------------------------------------------------

    def apply(self, event: EventDraft) -> bool:
        """Actualiza el estado con un evento del bus. Devuelve `False` si ya se había contado."""
        if event.type not in _HANDLED or event.event_id in self._seen:
            return False
        self._seen.add(event.event_id)
        match event.type:
            case EventType.DETECTION_RAISED | EventType.DETECTION_UPDATED:
                self._on_raised(event)
            case EventType.DETECTION_CLEARED:
                self._on_cleared(event)
            case EventType.ANOMALY_DETECTED:
                self._on_alert(event)
            case EventType.ALERT_CLOSED:
                self._on_closed(event)
            case EventType.DETECTION_ACKNOWLEDGED:
                self._on_ack(event)
        return True

    def _on_raised(self, event: EventDraft) -> None:
        p = DetectionRaised.model_validate(event.payload)
        record = self.detections.get(p.detection_id)
        if record is None:
            self.detections[p.detection_id] = DetectionRecord(
                p.detection_id,
                p.rule.value,
                p.source.value if p.source else None,
                p.severity.value,
                event.sim_time,
                opened_severity=p.severity.value,
                message=p.message,
                value=p.value,
                threshold=p.threshold,
                unit=p.unit,
            )
        else:  # DetectionUpdated: la misma detección, ahora más grave
            record.severity = p.severity.value
            record.updates.append((event.sim_time, p.severity.value, p.value, p.message))

    def _on_cleared(self, event: EventDraft) -> None:
        p = DetectionCleared.model_validate(event.payload)
        record = self.detections.get(p.detection_id)
        if record is not None:
            record.open = False
            record.closed_at = event.sim_time
            record.max_value = p.max_value

    def _on_alert(self, event: EventDraft) -> None:
        p = AnomalyDetected.model_validate(event.payload)
        alert = AlertRecord(
            p.alert_id,
            p.cause.value,
            p.severity.value,
            p.confidence,
            p.summary,
            event.sim_time,
            set(p.detection_ids),
            p.supersedes,
            fallback=p.fallback,
            explanation=p.explanation,
            recommendation=p.recommendation,
            evidence_ids=list(p.evidence_event_ids),
            checks=p.checks.model_dump() if p.checks else None,
        )
        previous = self.alerts.get(p.supersedes) if p.supersedes else None
        if previous is not None:
            previous.status = AlertStatus.SUPERSEDED
            previous.superseded_by = p.alert_id
            alert.detection_ids |= previous.detection_ids
        else:
            self.chains_published += 1
        self.alerts[p.alert_id] = alert
        for detection_id in p.detection_ids:
            record = self.detections.get(detection_id)
            if record is not None:
                record.alert_id = p.alert_id
        self._decide(
            event.sim_time,
            f"{', '.join(p.detection_ids)} → alert {p.alert_id} {p.cause.value} "
            f"({p.severity.value}, confidence {p.confidence:g})"
            + (f", supersedes {p.supersedes}" if p.supersedes else ""),
        )

    def _on_closed(self, event: EventDraft) -> None:
        p = AlertClosed.model_validate(event.payload)
        alert = self.alerts.get(p.alert_id)
        if alert is not None:
            alert.status = AlertStatus.CLOSED
            alert.closed_at = event.sim_time
        self._decide(event.sim_time, f"alert {p.alert_id} closed")

    def _on_ack(self, event: EventDraft) -> None:
        p = DetectionAcknowledged.model_validate(event.payload)
        record = self.detections.get(p.detection_id)
        alert = self.alerts.get(p.alert_id) if p.alert_id else None
        if record is not None and alert is not None:
            record.alert_id = alert.alert_id
            alert.detection_ids.add(p.detection_id)
        target = f"alert {p.alert_id}" if p.alert_id else "no alert"
        self._decide(event.sim_time, f"{p.detection_id} → acknowledged ({target})")

    def _decide(self, sim_time: float, text: str) -> None:
        self.decisions.append(f"{format_t(sim_time)} {text}")

    # --- Consultas ------------------------------------------------------------------------

    def head(self, alert_id: str | None) -> AlertRecord | None:
        """La alerta en vigor de la cadena a la que pertenece `alert_id`."""
        alert = self.alerts.get(alert_id) if alert_id else None
        while alert is not None and alert.superseded_by is not None:
            alert = self.alerts.get(alert.superseded_by)
        return alert

    def alert_of(self, detection_id: str) -> AlertRecord | None:
        """Alerta en vigor de la detección (abierta o cerrada), o `None` si no tiene."""
        record = self.detections.get(detection_id)
        return self.head(record.alert_id) if record else None

    def is_gps_alert(self, alert: AlertRecord) -> bool:
        """Alerta del GPS: spoofing o pérdida/interferencia, o un fallo de sensor cuyas
        detecciones son del GPS (`GPS_DEGRADED`, `SOURCE_SILENT` del GPS o discrepancia)."""
        if alert.cause in ("GPS_SPOOFING", "GPS_JAMMING"):
            return True
        if alert.cause != "SENSOR_FAULT":
            return False
        for detection in self.detections_of(alert.alert_id):
            if (
                detection.rule in ("GPS_DEGRADED", "SOURCE_DISCREPANCY")
                or detection.source == "gps"
            ):
                return True
        return False

    def recent_gps_alert(self, now: float, grace_s: float = 60.0) -> AlertRecord | None:
        """La alerta del GPS abierta, o cerrada hace `grace_s` s de tiempo simulado o menos (se
        miran las alertas en vigor de cada cadena; la abierta manda sobre la cerrada)."""
        recent: AlertRecord | None = None
        for alert in self.alerts.values():
            if alert.superseded_by is not None or not self.is_gps_alert(alert):
                continue
            if alert.status == AlertStatus.OPEN:
                return alert
            if alert.closed_at is not None and now - alert.closed_at <= grace_s:
                recent = alert
        return recent

    def gps_alert_recent(self, now: float, grace_s: float = 60.0) -> bool:
        return self.recent_gps_alert(now, grace_s) is not None

    def describe_gps_alert(self, now: float) -> str:
        """La línea fija del estado del prompt: «yes — ai-0008 GPS_SPOOFING (open). If this warning
        is the GPS recovery: cause GPS_SPOOFING, supersedes ai-0008» o «no»."""
        alert = self.recent_gps_alert(now)
        if alert is None:
            return "no"
        if alert.status == AlertStatus.OPEN:
            state, supersedes = "open", f"supersedes {alert.alert_id}"
        else:
            ago = now - (alert.closed_at or now)
            state, supersedes = f"closed {ago:.0f} s ago", "no supersedes (already closed)"
        return (
            f"yes — {alert.alert_id} {alert.cause} ({state}). If this warning is the GPS "
            f"recovery: cause {alert.cause}, {supersedes}"
        )

    def open_alerts(self) -> list[AlertRecord]:
        return [a for a in self.alerts.values() if a.status == AlertStatus.OPEN]

    def open_detections(self) -> list[DetectionRecord]:
        return [d for d in self.detections.values() if d.open]

    def detections_of(self, alert_id: str) -> list[DetectionRecord]:
        """Detecciones que pertenecen a la alerta en vigor `alert_id` (de toda la cadena)."""
        return [
            d for d in self.detections.values() if self.head(d.alert_id) is self.alerts[alert_id]
        ]

    def open_detections_of(self, alert_id: str) -> list[DetectionRecord]:
        return [d for d in self.detections_of(alert_id) if d.open]

    # --- Texto para el prompt (en inglés) ------------------------------------------------

    def describe_open_alerts(self) -> str:
        alerts = self.open_alerts()
        if not alerts:
            return "none"
        parts = []
        for a in alerts:
            members = ", ".join(
                f"{d.detection_id} ({'open' if d.open else 'closed'})"
                for d in self.detections_of(a.alert_id)
            )
            parts.append(
                f"{a.alert_id} {a.cause} ({a.severity}, confidence {a.confidence:g}) "
                f'"{a.summary}" · detections: {members or "none"}'
            )
        return "; ".join(parts)

    def describe_open_detections(self) -> str:
        detections = self.open_detections()
        if not detections:
            return "none"
        parts = []
        for d in detections:
            alert = self.head(d.alert_id)
            where = f"in alert {alert.alert_id}" if alert else "no alert"
            source = f" {d.source}" if d.source else ""
            parts.append(
                f"{d.detection_id} {d.rule}{source} ({d.severity}, since {format_t(d.since)}, "
                f"{where})"
            )
        return "; ".join(parts)

    def describe_decisions(self) -> str:
        return "; ".join(self.decisions) if self.decisions else "none yet"

    def describe_alert_chains(self) -> str:
        """Para el informe: una línea por cadena de alertas (la alerta en vigor y las que
        sustituyó) con sus detecciones y su estado final."""
        heads = [a for a in self.alerts.values() if a.superseded_by is None]
        if not heads:
            return "There were no alerts."
        lines = []
        for head in heads:
            chain = [head]
            while chain[-1].supersedes and chain[-1].supersedes in self.alerts:
                chain.append(self.alerts[chain[-1].supersedes])
            history = " ← ".join(
                f"{a.alert_id} {a.cause} ({a.severity}, confidence {a.confidence:g}) at "
                f"{format_t(a.sim_time)}"
                for a in chain
            )
            end = (
                f"closed at {format_t(head.closed_at)}"
                if head.closed_at is not None
                else "OPEN at the end"
            )
            detections = ", ".join(d.detection_id for d in self.detections_of(head.alert_id))
            fallback = " [fallback diagnosis: the agent did not conclude]" if head.fallback else ""
            lines.append(
                f'- {history}{fallback}: "{head.summary}" · detections: {detections or "none"}'
                f" · {end}"
            )
        return "\n".join(lines)

    def describe_detection_log(self) -> str:
        """Para el informe: una línea por detección (regla, inicio, cierre y alerta)."""
        if not self.detections:
            return "There were no detections."
        lines = []
        for d in self.detections.values():
            alert = self.head(d.alert_id)
            end = format_t(d.closed_at) if d.closed_at is not None else "still open"
            source = f" {d.source}" if d.source else ""
            where = f"alert {alert.alert_id}" if alert else "no alert"
            lines.append(
                f"- {d.detection_id} {d.rule}{source} ({d.severity}): "
                f"from {format_t(d.since)} to {end} · {where}"
            )
        return "\n".join(lines)

    def describe_alerts_detail(self, max_chars: int = 700, *, explanation: bool = True) -> str:
        """Para los chats sin tools: cada alerta con sus comprobaciones y sus evidencias y, si
        `explanation`, con el razonamiento en prosa del monitor (que puede contradecir sus propias
        comprobaciones: los chats lo reciben sin él)."""
        if not self.alerts:
            return "None."
        lines = []
        for a in self.alerts.values():
            state = {
                AlertStatus.OPEN: "open",
                AlertStatus.CLOSED: f"closed at {format_t(a.closed_at or 0)}",
                AlertStatus.SUPERSEDED: f"superseded by {a.superseded_by}",
            }[a.status]
            prose = (
                a.explanation
                if len(a.explanation) <= max_chars
                else (a.explanation[:max_chars] + "…")
            )
            checks = (
                "; ".join(
                    f"{CHECK_LABELS[k]}: {'yes' if v else 'no' if v is False else 'not looked at'}"
                    for k, v in a.checks.items()
                )
                if a.checks
                else "no checks (fallback alert)"
            )
            lines.append(
                f"- {a.alert_id} {a.cause} ({a.severity}, confidence {a.confidence:g}) at "
                f'{format_t(a.sim_time)}, {state}: "{a.summary}". '
                f"{f'Explanation: {prose} ' if explanation else ''}"
                f"Recommendation: {a.recommendation} Checks: {checks}. "
                f"Evidence: {', '.join(a.evidence_ids) or 'none'}."
            )
        return "\n".join(lines)

    def describe_related_alerts(self, detection_id: str) -> str:
        alert = self.alert_of(detection_id)
        if alert is None:
            return "none"
        return f"{alert.alert_id} ({alert.cause}, {alert.severity}, {alert.status.value})"


_HANDLED = frozenset(
    {
        EventType.DETECTION_RAISED,
        EventType.DETECTION_UPDATED,
        EventType.DETECTION_CLEARED,
        EventType.ANOMALY_DETECTED,
        EventType.ALERT_CLOSED,
        EventType.DETECTION_ACKNOWLEDGED,
    }
)
