"""Ids de los eventos que publica el módulo de IA (`ai-0001`, `inv-0001`…).

Un solo contador por prefijo para toda la ejecución: el `alert_id` de una alerta es el
`event_id` de su `AnomalyDetected`. Se reinicia al empezar o reiniciar la simulación.
"""


class IdAllocator:
    def __init__(self) -> None:
        self._counters: dict[str, int] = {}

    def next(self, prefix: str, width: int = 4) -> str:
        """Siguiente id con ese prefijo: `next("ai")` -> `ai-0001`."""
        number = self._counters.get(prefix, 0) + 1
        self._counters[prefix] = number
        return f"{prefix}-{number:0{width}d}"

    def reset(self) -> None:
        self._counters.clear()
