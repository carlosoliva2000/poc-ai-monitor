"""Servidor falso compatible con la API Chat Completions de OpenAI (solo la biblioteca estándar).

Sirve para probar el módulo de IA de extremo a extremo sin vLLM: `serve(policy)` escucha en un
puerto libre de `127.0.0.1` y contesta cada petición con lo que decida `policy(body)`, que
devuelve `{"content": str, "tool_calls": [(nombre, argumentos)]}`. Soporta `stream: true` (SSE) con
`stream_options.include_usage`.
"""

import json
import threading
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

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

    def log_message(self, *args: Any) -> None:  # silencio
        pass

    def do_POST(self) -> None:
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        self.requests.append(body)
        decision = type(self).policy(body)
        message = _message(decision)
        if body.get("stream"):
            self._stream(message)
            return
        payload = {
            "id": "chatcmpl-fake",
            "object": "chat.completion",
            "created": 0,
            "model": body["model"],
            "choices": [{"index": 0, "message": message, "finish_reason": "stop"}],
            "usage": USAGE,
        }
        self._send(200, json.dumps(payload).encode(), "application/json")

    def do_GET(self) -> None:
        self._send(200, b'{"object":"list","data":[{"id":"fake-model"}]}', "application/json")

    def _send(self, status: int, data: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _stream(self, message: dict[str, Any]) -> None:
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


class FakeLlmServer:
    def __init__(self, policy: Policy) -> None:
        handler = type("BoundHandler", (Handler,), {"policy": staticmethod(policy), "requests": []})
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
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
