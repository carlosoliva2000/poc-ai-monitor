"""La verdad del ejercicio frente a lo detectado, escrita por el código para el instructor.

Lo programado (`ExerciseInjects`), los fallos inyectados a mano y los comandos de viento del
instructor son los «episodios»; cada uno se empareja con el incidente que lo vio (o no). El LLM
solo copia estas conclusiones: nunca decide si algo se detectó. Solo existe en el proceso del
instructor.
"""

from dataclasses import dataclass
from typing import Any

from poc_contracts.enums import IncidentKind

from ..outbox import format_t
from .store import InstructorStore

SLACK_BEFORE_S = 15.0  # un incidente que abre antes de esto no es de este episodio
SLACK_AFTER_S = 90.0  # ni el que abre mucho después de que termine
K = IncidentKind
SEEN_AS: dict[str, set[IncidentKind]] = {
    "wind": {K.WIND, K.UNDETERMINED},
    "hijack": {K.LINK_LOSS, K.HIJACK},
    "gps_spoofing": {K.GPS_SPOOFING},
    "gps_loss": {K.GPS_NO_FIX, K.DEAD_RECKONING},
    "gps_degraded": {K.GPS_DEGRADED, K.GPS_NO_FIX},
    "link_degraded": {K.LINK_DEGRADED, K.LINK_LOSS},
    "source_silent": {K.SOURCE_SILENT},
}
# El tipo de incidente que nombra cada tipo de episodio (las causas que el chat puede decir)
CAUSE_OF = {"wind": K.WIND, "hijack": K.HIJACK, "gps_spoofing": K.GPS_SPOOFING,
            "gps_loss": K.DEAD_RECKONING}  # fmt: skip
WORDS = {
    "wind": "wind", "hijack": "hijack of the drone", "gps_spoofing": "GPS spoofing",
    "gps_loss": "GPS loss", "gps_degraded": "GPS degradation",
    "link_degraded": "command link degradation", "source_silent": "source silenced",
}  # fmt: skip


@dataclass
class Episode:
    kind: str  # tipo de `labels.json`
    source: str | None
    start: float
    end: float | None
    origin: str  # `programmed`, `manual` o `instructor`

    def describe(self) -> str:
        what = WORDS.get(self.kind, self.kind)
        if self.source and self.kind == "source_silent":
            what = f"{self.source} silenced"
        end = "until the end" if self.end is None else f"to {format_t(self.end)}"
        return f"{what} ({self.origin}) from {format_t(self.start)} {end}"


def episodes(store: InstructorStore) -> list[Episode]:
    out = [
        Episode(i["type"], i["source"], i["start_s"], i["end_s"], "programmed")
        for i in store.injects
    ]
    for fault in store.faults:
        if fault.get("origin") == "scenario":
            continue  # ya está en lo programado
        kind = "gps_loss" if fault["mode"] == "loss" else "source_silent"
        out.append(Episode(kind, fault["source"], fault["start"], fault["end"], "manual"))
    wind: Episode | None = None
    for command in store.commands:
        if command.get("issued_by") == "scenario":
            continue
        if wind is not None and wind.end is None:
            wind.end = command["t"]
        if command["command"] == "set_wind":
            duration = command["params"]["duration_s"]
            end = None if duration is None else command["t"] + duration
            wind = Episode("wind", None, command["t"], end, "instructor")
            out.append(wind)
        else:
            wind = None
    return sorted(out, key=lambda e: e.start)


def incident_spans(store: InstructorStore) -> list[dict[str, Any]]:
    spans = []
    for revisions in store.revisions.values():
        spans.append(
            {
                "kinds": {K(r["kind"]) for r in revisions},
                "subjects": {r.get("subject") for r in revisions},
                "opened": revisions[0]["opened_at"],
                "first": revisions[0]["name"],
                "last": revisions[-1]["name"],
            }
        )
    return spans


def pairing(store: InstructorStore) -> list[str]:
    """Una línea por episodio: qué incidente lo vio y cuándo, o que no se vio."""
    lines: list[str] = []
    delays: list[tuple[float, str]] = []
    spans = incident_spans(store)
    for ep in episodes(store):
        expected = SEEN_AS.get(ep.kind, set())
        end = ep.end if ep.end is not None else store.now
        found = [
            s for s in spans
            if s["kinds"] & expected
            and ep.start - SLACK_BEFORE_S <= s["opened"] <= end + SLACK_AFTER_S
            and (ep.kind != "source_silent" or ep.source in s["subjects"] or ep.source == "link")
        ]  # fmt: skip
        if found:
            best = min(found, key=lambda s: abs(s["opened"] - ep.start))
            delay = best["opened"] - ep.start
            when = (
                f"{abs(delay):.0f} s after it started" if delay >= 0
                else f"{abs(delay):.0f} s before it started"
            )  # fmt: skip
            name = (
                best["first"]
                if best["first"] == best["last"]
                else f"{best['first']}, later {best['last']}"
            )
            lines.append(
                f"- {ep.describe()}: Detected as {name}, "
                f"opened at {format_t(best['opened'])} ({when})"
            )
            delays.append((delay, ep.describe()))
        elif ep.start > store.now:
            lines.append(f"- {ep.describe()}: Has not started yet")
        elif ep.end is None or store.now <= ep.end + SLACK_AFTER_S:
            lines.append(f"- {ep.describe()}: Not detected yet (it is still in progress)")
        else:
            lines.append(f"- {ep.describe()}: Not detected")
    if len(delays) > 1:  # el orden de los retrasos lo da el código: el modelo comparaba mal
        slowest = max(delays)
        lines.append(f"Slowest detection: {slowest[1]}, {slowest[0]:.0f} s after it started")
    return lines


def truth_causes(store: InstructorStore) -> set[IncidentKind]:
    return {CAUSE_OF[e.kind] for e in episodes(store) if e.kind in CAUSE_OF}
