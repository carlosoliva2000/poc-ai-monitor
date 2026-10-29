"""Servidor falso compatible con la API Chat Completions de OpenAI (servidor HTTP estándar).

Sirve para probar el módulo de IA de extremo a extremo sin vLLM: `FakeLlmServer(policy)` escucha
en un puerto libre de `127.0.0.1` y contesta cada petición con lo que decida `policy(body)`, que
devuelve `{"content": str, "tool_calls": [(nombre, argumentos)]}`. Soporta `stream: true` (SSE) con
`stream_options.include_usage`, `/health`, `/version` y `/v1/models` (con el modelo de
`agents.yaml` o el que se pida), y, si la petición enciende el razonamiento
(`chat_template_kwargs.enable_thinking`), devuelve un `reasoning` falso y sus tokens.

También se puede lanzar como servidor aparte (lo usa `run_matrix --fake`):

    uv run --project ai-module-py python -m ai_module.testing.fake_llm --port 8000
"""

import argparse
import json
import re
import threading
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import yaml

from ..agent.assets import DEFAULT_ASSETS

FAKE_REASONING = "Fake reasoning of the step."
FAKE_REASONING_TOKENS = 5

Policy = Callable[[dict[str, Any]], dict[str, Any]]


def _message(decision: dict[str, Any]) -> dict[str, Any]:
    message: dict[str, Any] = {"role": "assistant", "content": decision.get("content") or None}
    calls = decision.get("tool_calls") or []
    if calls:
        message["tool_calls"] = [
            {
                "id": f"call-{i}",
                "type": "function",
                "function": {"name": name, "arguments": json.dumps(arguments)},
            }
            for i, (name, arguments) in enumerate(calls)
        ]
    return message


USAGE = {"prompt_tokens": 100, "completion_tokens": 10, "total_tokens": 110}


class Handler(BaseHTTPRequestHandler):
    policy: Policy
    requests: list[dict[str, Any]]
    model: str

    def log_message(self, *args: Any) -> None:  # silencio
        pass

    def do_POST(self) -> None:
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        self.requests.append(body)
        decision = type(self).policy(body)
        message = _message(decision)
        thinking = (body.get("chat_template_kwargs") or {}).get("enable_thinking") is True
        if thinking:
            message["reasoning"] = FAKE_REASONING
        if body.get("stream"):
            self._stream(message, thinking)
            return
        payload = {
            "id": "chatcmpl-fake",
            "object": "chat.completion",
            "created": 0,
            "model": body["model"],
            "choices": [{"index": 0, "message": message, "finish_reason": "stop"}],
            "usage": USAGE
            | (
                {"completion_tokens_details": {"reasoning_tokens": FAKE_REASONING_TOKENS}}
                if thinking
                else {}
            ),
        }
        self._send(200, json.dumps(payload).encode(), "application/json")

    def do_GET(self) -> None:
        if self.path == "/version":
            self._send(200, b'{"version":"fake"}', "application/json")
        elif self.path.endswith("/models"):
            data = {"object": "list", "data": [{"id": type(self).model}]}
            self._send(200, json.dumps(data).encode(), "application/json")
        else:  # /health
            self._send(200, b"{}", "application/json")

    def _send(self, status: int, data: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _stream(self, message: dict[str, Any], thinking: bool = False) -> None:
        def chunk(delta: dict[str, Any], finish: str | None = None, usage: Any = None) -> bytes:
            body = {
                "id": "chatcmpl-fake",
                "object": "chat.completion.chunk",
                "created": 0,
                "model": "fake-model",
                "choices": [] if usage else [{"index": 0, "delta": delta, "finish_reason": finish}],
                "usage": usage,
            }
            return b"data: " + json.dumps(body).encode() + b"\n\n"

        out = chunk({"role": "assistant"})
        if thinking:
            out += chunk({"reasoning": FAKE_REASONING})
        for word in (message["content"] or "").split(" "):
            if word:
                out += chunk({"content": word + " "})
        for index, call in enumerate(message.get("tool_calls", [])):
            out += chunk(
                {
                    "tool_calls": [
                        {
                            "index": index,
                            "id": call["id"],
                            "type": "function",
                            "function": {"name": call["function"]["name"], "arguments": ""},
                        }
                    ]
                }
            )
            out += chunk(
                {
                    "tool_calls": [
                        {"index": index, "function": {"arguments": call["function"]["arguments"]}}
                    ]
                }
            )
        out += chunk({}, "stop") + chunk({}, usage=USAGE) + b"data: [DONE]\n\n"
        self._send(200, out, "text/event-stream")


def default_model() -> str:
    """El modelo de `agents.yaml`, para que el módulo de IA pase su comprobación al arrancar."""
    raw = yaml.safe_load((DEFAULT_ASSETS / "agents.yaml").read_text(encoding="utf-8"))
    return str(raw["llm"]["model"])


class FakeLlmServer:
    def __init__(self, policy: Policy, port: int = 0, model: str | None = None) -> None:
        """`model`: lo que contesta `/v1/models` (por defecto, el modelo de `agents.yaml`)."""
        handler = type(
            "BoundHandler",
            (Handler,),
            {"policy": staticmethod(policy), "requests": [], "model": model or default_model()},
        )
        self.httpd = ThreadingHTTPServer(("127.0.0.1", port), handler)
        self.requests: list[dict[str, Any]] = handler.requests
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.httpd.server_address[1]}/v1"

    def __enter__(self) -> "FakeLlmServer":
        self.thread.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()


def demo_policy(body: dict[str, Any]) -> dict[str, Any]:
    """Decisión del LLM falso según el prompt: monitor, informe o chat."""
    system = body["messages"][0]["content"]
    messages = body["messages"]
    if "report agent" in system:
        text = "## Resumen\n\nInforme de prueba.\n\n## Valoración del monitor\n\nSegún los eventos."
        return {"content": text}
    if "now the human **operator** is talking to you" in system:
        return {"content": "Respuesta de prueba del chat con datos."}
    user = messages[1]["content"]
    pending = list(dict.fromkeys(re.findall(r"(?:detection|New detection) (det-\d+)", user)))
    last_open = re.search(r"of alert (ai-\d+)", user)
    open_alert = re.search(r"Open alerts: (ai-\d+)", user)
    if last_open:
        return {"tool_calls": [("close_alert", {"alert_id": last_open.group(1), "reason": "ok"})]}
    if open_alert:
        args = {"detection_ids": pending, "alert_id": open_alert.group(1), "reason": "igual"}
        return {"tool_calls": [("acknowledge_detection", args)]}
    triggers = re.search(r'"trigger_event_ids":\[([^\]]*)\]', user)
    ids = re.findall(r'"([^"]+)"', triggers.group(1) if triggers else "") or ["gps-000001"]
    checks = {"gps_alert_recent": False, "gps_radar_disagreed": False, "wind_notable": False,
              "wind_with_drift": False, "link_checked": False, "link_anomalous": None}  # fmt: skip
    alert = {"detection_ids": pending, "checks": checks, "cause": "UNKNOWN", "severity": "medium",
             "confidence": 0.4, "summary": "prueba", "explanation": "e", "recommendation": "r",
             "evidence_event_ids": ids[:2]}  # fmt: skip
    return {"tool_calls": [("publish_alert", alert)]}


def main() -> None:
    parser = argparse.ArgumentParser(description="Fake LLM server with the e2e demo policy")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--model", help="model name that /v1/models reports (default: agents.yaml)")
    args = parser.parse_args()
    server = FakeLlmServer(demo_policy, args.port, args.model)
    server.thread.start()
    print(f"fake LLM at {server.url}", flush=True)
    server.thread.join()


if __name__ == "__main__":
    main()
