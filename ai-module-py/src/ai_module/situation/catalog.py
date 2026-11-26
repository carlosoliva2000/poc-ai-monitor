"""Catálogo de incidentes: qué combinación de estados de las facetas abre cada tipo.

Es política (la escribimos nosotros), no aprendida. Entra la vista de un instante (el estado y la
confianza de cada faceta, ya enmascarados como al entrenar) y sale, por familia, el tipo que se
propone. Las reglas de lectura son estas:
- **máscaras:** con el enlace perdido, el GPS y la batería no son observables (`?`); con una
  entidad no disponible, sus otras facetas no aplican (`n/a`); sin desviación no hay causa. Un `?`
  o un `n/a` ni abre un incidente ni cuenta como «la causa ha desaparecido»;
- **confianza:** una fila `possible` no abre nada, salvo las fuentes sin datos (que son un hecho,
  no una causa) y, como «sin determinar», una causa dudosa que nada explica;
- **una desviación explicada por un incidente abierto** (de enlace, GPS, engaño o viento) es
  evidencia de ese incidente, no un «sin determinar»;
- **los failsafes** son contexto del incidente que los provoca (enlace, batería) y solo son
  incidente propio si nada lo explica.
Dentro de una familia, las reglas van de más a menos grave y gana la primera que encaja.
"""

from dataclasses import dataclass, field

from poc_contracts.enums import IncidentKind

from .policy import Policy

CONF = {"possible": 0, "probable": 1, "confirmed": 2}
FAILSAFE_MODES = ("failsafe_hold", "failsafe_return", "failsafe_land")
SOURCES = ("gps", "radar", "meteo", "battery")
TELEMETRY = ("gps", "battery")  # solo llegan si llega el paquete del dron
NOT_OBSERVABLE = "?"
NOT_APPLICABLE = "n/a"


@dataclass(frozen=True)
class Candidate:
    family: str  # familia efectiva (`source:radar` para una fuente)
    kind: IncidentKind
    subject: str | None
    confidence: str


@dataclass
class View:
    """Un instante tal como lo lee el catálogo."""

    states: dict[str, str]
    conf: dict[str, str] = field(default_factory=dict)
    open_families: frozenset[str] = frozenset()  # familias con un incidente abierto o recuperando
    explained_failsafe: bool = False  # el failsafe actual ya lo explica otro incidente

    def state(self, facet: str) -> str:
        return self.states.get(facet, NOT_APPLICABLE)

    def level(self, facet: str) -> int:
        return CONF[self.conf.get(facet, "confirmed")]

    def is_(self, facet: str, *states: str, minimum: str = "probable") -> bool:
        return self.state(facet) in states and self.level(facet) >= CONF[minimum]


def mask(states: dict[str, str]) -> dict[str, str]:
    """Las facetas que no se pueden leer ahora, como al entrenar: `?` y `n/a`."""
    out = dict(states)
    if out.get("link.availability") == "lost":  # sin enlace no llega la telemetría del dron
        for facet in ("gps.availability", "gps.quality", "gps.integrity", "battery.availability",
                      "battery.level", "battery.endurance"):  # fmt: skip
            out[facet] = NOT_OBSERVABLE
        out["link.quality"] = NOT_APPLICABLE
    for entity, others in (
        ("gps", ("gps.quality", "gps.integrity")),
        ("battery", ("battery.level", "battery.endurance")),
    ):
        if out.get(f"{entity}.availability") not in ("normal", None):
            for facet in others:
                out[facet] = NOT_APPLICABLE
    if out.get("drone.situation", "on_route") == "on_route":
        out["drone.cause"] = NOT_APPLICABLE
    return out


def hijack_level(view: View) -> int:
    """Nivel de la evidencia de control ajeno: la causa (con el dron desviado) **y** el modo del
    autopiloto tienen que decirlo; vale el más débil de los dos (con uno solo, `-1`). Un corte del
    enlace con el dron siguiendo su plan o volviendo a casa, o girando una esquina sin telemetría,
    puede parecerle «control ajeno» a la causa sola: con las dos tablas de acuerdo, no."""
    levels = [
        view.level(facet) if view.state(facet) == "foreign_control" else -1
        for facet in ("drone.cause", "drone.mode")
    ]
    return min(levels)


def decision_confidence(view: View, policy: Policy, kind: IncidentKind, subject: str | None) -> str:
    """Nivel del incidente: el mejor de las facetas que lo deciden (si ninguna, `possible`)."""
    kind_policy = policy.kinds[kind]
    sub = kind_policy.subjects.get(subject or "")
    best = -1
    for facet, wanted in kind_policy.decided_by.items():
        if sub and sub.facet and facet.endswith(".availability") and facet != sub.facet:
            continue
        if view.state(facet) in wanted:
            best = max(best, view.level(facet))
    return next((name for name, level in CONF.items() if level == best), "possible")


def _find(view: View) -> list[tuple[str, IncidentKind, str | None]]:
    """Todas las coincidencias `(familia efectiva, tipo, sujeto)`, de más a menos grave."""
    found: list[tuple[str, IncidentKind, str | None]] = []
    K = IncidentKind
    is_ = view.is_
    lost = view.state("link.availability") == "lost" and view.level("link.availability") >= 1
    # enlace y control
    if lost and hijack_level(view) >= CONF["confirmed"]:
        found.append(("control", K.HIJACK, None))
    elif lost:
        found.append(("control", K.LINK_LOSS, None))
    elif is_("link.quality", "degraded"):
        found.append(("control", K.LINK_DEGRADED, None))
    # GPS
    if is_("drone.cause", "dead_reckoning"):
        found.append(("gnss", K.DEAD_RECKONING, None))
    elif is_("gps.availability", "no_fix"):
        found.append(("gnss", K.GPS_NO_FIX, None))
    elif is_("gps.quality", "degraded"):
        found.append(("gnss", K.GPS_DEGRADED, None))
    if is_("gps.integrity", "spoofed"):
        found.append(("spoofing", K.GPS_SPOOFING, None))
    # viento
    # el salto del GPS al acabar un engaño lo ve el estimador como un viento falso unos segundos
    # (y el del GPS que vuelve tras una pérdida, con el estimador reenganchándose)
    false_wind = bool(view.open_families & {"spoofing", "gnss"})
    # y la causa «viento» de las tablas es la más probable cuando falta información: con otra
    # causa en curso (la causa de la etiqueta es pegajosa) no se cuenta
    other_cause = bool(view.open_families & {"spoofing", "gnss", "control"})
    by_cause = is_("drone.cause", "wind") and not other_cause
    if (is_("environment.wind", "beyond_limit") and not false_wind) or by_cause:
        found.append(("wind", K.WIND, None))
    # batería y failsafe
    if is_("battery.level", "critical"):
        found.append(("battery", K.BATTERY_CRITICAL, None))
    elif is_("battery.endurance", "cannot_reach_home") and view.state("drone.mode") == "mission":
        found.append(("battery", K.CANNOT_REACH_HOME, None))
    elif is_("battery.level", "low"):
        found.append(("battery", K.BATTERY_LOW, None))
    elif view.state("drone.mode") in FAILSAFE_MODES and not view.explained_failsafe:
        found.append(("battery", K.FAILSAFE, view.state("drone.mode")))
    # fuentes sin datos y radar
    # sin enlace, recién vuelto o con pérdida de paquetes, la telemetría del dron falta
    link_gap = "control" in view.open_families or view.state("link.quality") == "degraded"
    for source in SOURCES:
        if source in TELEMETRY and link_gap:
            continue
        if view.is_(f"{source}.availability", "no_data", minimum="possible"):
            found.append((f"source:{source}", K.SOURCE_SILENT, source))
    if is_("radar.availability", "out_of_range"):
        found.append(("radar", K.RADAR_OUT_OF_RANGE, None))
    return found


def candidates(view: View, policy: Policy) -> dict[str, Candidate]:
    """El tipo propuesto por cada familia en este instante."""
    out: dict[str, Candidate] = {}
    for family, kind, subject in _find(view):
        if family not in out:
            out[family] = Candidate(
                family, kind, subject, decision_confidence(view, policy, kind, subject)
            )
    # desviación sin explicar: «sin determinar» (causa dudosa o desconocida)
    explainers = set(policy.explains_deviation)
    explained = bool(view.open_families & explainers) or bool(set(out) & explainers)
    if view.state("drone.situation") == "deviated" and not explained:
        out["undetermined"] = Candidate("undetermined", IncidentKind.UNDETERMINED, None, "possible")
    return out
