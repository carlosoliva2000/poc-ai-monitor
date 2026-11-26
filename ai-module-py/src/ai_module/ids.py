"""Ids de los eventos que publica el módulo de IA (`ai-0001`, `inv-0001`…).

Un solo contador por prefijo para toda la ejecución: el `alert_id` de una alerta es el
`event_id` de su `AnomalyDetected`. Se reinicia al empezar o reiniciar la simulación.
"""

# Prefijos de evento que comparten los procesos del módulo en el mismo bus (que rechaza un id
# repetido): llevan la etiqueta del proceso, `ai-m-0001` (monitor), `ai-a-0001` (asistente del
# alumno), `ai-i-0001` (asistente del instructor). El resto (`inc-`, `inv-`) no se comparte.
SHARED_PREFIXES = frozenset({"ai", "act", "chk"})


class IdAllocator:
    """Un contador por prefijo. Con `tag`, los prefijos compartidos entre procesos llevan la
    etiqueta del proceso (`ai-a-0001`): no se pisan por muchos eventos que haya. Sin `tag`
    (herramientas fuera de línea y pruebas), `ai-0001`."""

    def __init__(self, tag: str | None = None) -> None:
        if tag is not None and not (len(tag) == 1 and tag.isalpha() and tag.islower()):
            raise ValueError(f"the process tag is one lowercase letter, not {tag!r}")
        self._counters: dict[str, int] = {}
        self.tag = tag

    def next(self, prefix: str, width: int = 4) -> str:
        """El siguiente id: `next("ai")` da `ai-0001`; con la etiqueta `a`, `ai-a-0001`."""
        number = self._counters.get(prefix, 0) + 1
        self._counters[prefix] = number
        tagged = f"{prefix}-{self.tag}" if self.tag and prefix in SHARED_PREFIXES else prefix
        return f"{tagged}-{number:0{width}d}"

    def reset(self) -> None:
        self._counters.clear()
