"""Utilidades de las pruebas de los agentes: LLM falso guionizado, plataforma falsa y eventos."""

import asyncio
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from ai_module.agent.assets import Assets
from ai_module.agent.llm import DeltaCallback, LlmResponse, Messages, ToolCall
from ai_module.runtime import Runtime
from poc_contracts.enums import EventType
from poc_contracts.envelope import Envelope
from poc_contracts.topics import EVENT_SPECS, asset_for, routing_for, source_for, topic_for

Policy = Callable[[Messages, list[dict[str, Any]], dict[str, Any]], LlmResponse | str | Exception]


def call(_name: str, **arguments: Any) -> ToolCall:
    return ToolCall(id=f"call-{_name}", name=_name, arguments=json.dumps(arguments))


def tool_response(*calls: ToolCall, content: str = "") -> LlmResponse:
    # `finish_reason: stop` aunque haya llamadas: el motor no debe mirarlo
    return LlmResponse(content, list(calls), "stop", 100, 20, 0.01)


def text_response(text: str) -> LlmResponse:
    return LlmResponse(text, [], "stop", 100, 20, 0.01)


class FakeLlm:
    """LLM falso: `policy(messages, tools, sampling)` devuelve la respuesta (o un texto, o una
    excepción que se lanza). Guarda las peticiones recibidas."""

    model = "fake-model"

    def __init__(self, policy: Policy) -> None:
        self.policy = policy
        self.requests: list[dict[str, Any]] = []

    async def complete(
        self,
        messages: Messages,
        tools: list[dict[str, Any]],
        sampling: dict[str, Any],
        *,
        stream: bool = False,
        on_delta: DeltaCallback | None = None,
        timeout_s: float | None = None,
    ) -> LlmResponse:
        self.requests.append(
            {
                "messages": json.loads(json.dumps(messages)),
                "tools": tools,
                "sampling": sampling,
                "stream": stream,
                "timeout_s": timeout_s,
            }  # fmt: skip
        )
        result = self.policy(messages, tools, sampling)
        if isinstance(result, Exception):
            raise result
        if isinstance(result, str):
            result = text_response(result)
        if stream and on_delta is not None and result.content:
            for word in result.content.split(" "):
                await on_delta(word + " ")
        return result


class Script:
    """Política que devuelve las respuestas en orden; la última se repite."""

    def __init__(self, *responses: LlmResponse | str | Exception) -> None:
        self.responses = list(responses)
        self.i = 0

    def __call__(self, messages: Messages, tools: list[dict], sampling: dict) -> Any:
        response = self.responses[min(self.i, len(self.responses) - 1)]
        self.i += 1
        return response


class FakePlatform:
    """Sustituye a `call_platform_tool`: resultados enlatados por tool y registro de llamadas."""

    def __init__(self, results: dict[str, Any] | None = None) -> None:
        self.results = results or {}
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def __call__(self, url: str, name: str, args: dict[str, Any], timeout_s: float = 10.0):
        self.calls.append((name, args))
        value = self.results.get(name, {})
        return value(args) if callable(value) else value


def make_runtime(
    tmp_path: Path, llm: FakeLlm, platform: FakePlatform | None = None
) -> tuple[Runtime, list[Any]]:
    """Runtime con un bus falso: lo publicado se acumula en la lista devuelta."""
    published: list[Any] = []

    async def publish(event: Any) -> None:
        published.append(event)

    rt = Runtime(
        Assets(),
        llm,
        "http://platform",
        publish,
        tmp_path,
        platform_call=platform or FakePlatform(),
    )
    return rt, published


_counters: dict[str, int] = {}


def reset_ids() -> None:
    _counters.clear()


def detection_event(
    kind: str,
    detection_id: str,
    sim_time: float,
    *,
    rule: str = "ROUTE_DEVIATION",
    source: str | None = None,
    event_id: str | None = None,
    trigger: tuple[str, ...] = ("gps-000001", "gps-000002"),
    severity: str = "medium",
) -> Envelope:
    """`DetectionRaised`/`Updated`/`Cleared` como Envelope. El `event_id` es el de la detección
    para el Raised y uno nuevo para los demás, como en el detector."""
    event_type = {
        "raised": EventType.DETECTION_RAISED,
        "updated": EventType.DETECTION_UPDATED,
        "cleared": EventType.DETECTION_CLEARED,
    }[kind]
    _counters["det"] = _counters.get("det", 0) + 1
    if kind == "cleared":
        payload: dict[str, Any] = {
            "detection_id": detection_id,
            "rule": rule,
            "duration_s": 20.0,
            "max_value": 40.0,
        }
    else:
        payload = {
            "detection_id": detection_id,
            "rule": rule,
            "severity": severity,
            "value": 35.0,
            "threshold": 30.0,
            "unit": {"SOURCE_SILENT": "s", "GPS_DEGRADED": "hdop"}.get(rule, "m"),
            "source": source,
            "window": {"since": sim_time - 2, "until": sim_time},
            "trigger_event_ids": list(trigger),
            "message": "desviación de prueba",
        }
    spec = EVENT_SPECS[event_type]
    return Envelope(
        event_id=event_id or (detection_id if kind == "raised" else f"det-9{_counters['det']:03d}"),
        topic=topic_for(event_type),
        type=event_type,
        source=source_for(event_type),
        asset=asset_for(spec.domain, routing_for(event_type)),
        seq=_counters["det"],
        sim_time=sim_time,
        event_time="2026-10-20T10:00:00Z",
        ingestion_time="2026-10-20T10:00:00.000Z",
        payload=payload,
    )


def seed_evidence(rt: Runtime, *ids: str, sim_time: float = 1.0) -> None:
    """Marca ids como eventos existentes (como si hubieran llegado por el WebSocket)."""
    from poc_contracts.envelope import EventDraft

    for event_id in ids:
        rt.index.add(
            EventDraft(
                event_id=event_id,
                topic="citadel.pub.evt.air.d1.PositionUpdated.v1",
                type=EventType.POSITION_UPDATED,
                source="d1-gps",
                asset="d1",
                sim_time=sim_time,
                event_time="2026-10-20T10:00:00Z",
                payload={
                    "x": 0.0,
                    "y": 0.0,
                    "alt_m": 60.0,
                    "speed_mps": 15.0,
                    "heading_deg": 0.0,
                    "fix": "3d",
                    "sats": 14,
                    "hdop": 0.8,
                },  # fmt: skip
            )
        )


NO_CHECKS: dict[str, Any] = {
    "gps_alert_recent": False,
    "gps_radar_disagreed": False,
    "wind_notable": False,
    "wind_with_drift": False,
    "link_checked": False,
    "link_anomalous": None,
}


THINKING_OFF = {"chat_template_kwargs": {"enable_thinking": False}}
"""`extra_body` de las peticiones con la configuración por defecto (Qwen3 sin razonamiento)."""


def alert_args(detection_ids: list[str], **overrides: Any) -> dict[str, Any]:
    """Argumentos válidos de `publish_alert` sin haber llamado a ninguna tool de datos: causa
    `UNKNOWN` y todos los `checks` en falso (que es lo que esperan el estado y las tools)."""
    args: dict[str, Any] = {
        "detection_ids": detection_ids,
        "checks": dict(NO_CHECKS),
        "cause": "UNKNOWN",
        "severity": "medium",
        "confidence": 0.4,
        "summary": "Causa desconocida",
        "explanation": "No hay datos suficientes.",
        "recommendation": "Revisión por el operador.",
        "evidence_event_ids": ["gps-000001", "gps-000002"],
    }
    args.update(overrides)
    return args


def run(coro: Any) -> Any:
    return asyncio.run(coro)
