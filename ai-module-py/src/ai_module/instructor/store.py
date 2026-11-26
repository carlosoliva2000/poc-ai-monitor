"""Lo que el proceso del instructor guarda del bus: lo mismo que el del alumno más la verdad del
ejercicio (lo programado, los fallos inyectados y los comandos del instructor)."""

from typing import Any

from ..assistant.store import ALLOWED_TYPES, Store

TRUTH_TYPES = frozenset({"ExerciseInjects", "FaultInjected", "FaultCleared", "InstructorCommand"})


class InstructorStore(Store):
    def __init__(self, cn0_nominal_dbhz: float = 45.0, agc_nominal_db: float = 0.0) -> None:
        super().__init__(cn0_nominal_dbhz, agc_nominal_db)

    def reset(self) -> None:
        super().reset()
        self.scenario: str | None = None
        self.injects: list[dict[str, Any]] = []  # lo programado (de `labels.json`)
        self.faults: list[dict[str, Any]] = []  # fallos: {source, mode, origin, start, end|None}
        self.commands: list[dict[str, Any]] = []  # comandos del instructor aplicados
        self.finished = False

    def observe(self, event: dict[str, Any]) -> bool:
        kind = event["type"]
        if kind not in TRUTH_TYPES:
            return super().observe(event) if kind in ALLOWED_TYPES else False
        payload, t = event["payload"], float(event["sim_time"])
        self.now = max(self.now, t)
        if kind == "ExerciseInjects":
            self.injects = list(payload["injects"])
        elif kind == "FaultInjected":
            self.faults.append({**payload, "start": t, "end": None})
        elif kind == "FaultCleared":
            for fault in reversed(self.faults):
                same = (fault["source"], fault["mode"]) == (payload["source"], payload["mode"])
                if same and fault["end"] is None:
                    fault["end"] = t
                    break
        elif kind == "InstructorCommand":
            self.commands.append({**payload, "t": t})
        return True

    def active_wind(self) -> dict[str, Any] | None:
        """El viento del instructor en curso, sacado de los comandos del bus (no de lo que diga la
        web): `{from_deg, speed_mps, remaining_s}` (`remaining_s` `None` = sin fin)."""
        active: dict[str, Any] | None = None
        for command in self.commands:
            if command["command"] == "cancel_wind":
                active = None
            elif command["command"] == "set_wind":
                params = command["params"]
                end = None if params["duration_s"] is None else command["t"] + params["duration_s"]
                active = {"from_deg": params["from_deg"], "speed_mps": params["speed_mps"],
                          "end": end}  # fmt: skip
        if active is None:
            return None
        if active["end"] is not None and self.now >= active["end"]:
            return None
        remaining = None if active["end"] is None else round(active["end"] - self.now)
        return {"from_deg": active["from_deg"], "speed_mps": active["speed_mps"],
                "remaining_s": remaining}  # fmt: skip

    def snapshot(self) -> "InstructorStore":
        copy = InstructorStore(self.cn0_nominal_dbhz, self.agc_nominal_db)
        base = super().snapshot()
        for name in ("now", "route", "last", "revisions", "event_ids", "texts", "report"):
            setattr(copy, name, getattr(base, name))
        copy.injects = list(self.injects)
        copy.faults = [dict(f) for f in self.faults]
        copy.commands = list(self.commands)
        copy.scenario = self.scenario
        copy.finished = self.finished
        return copy
