# poc-ai-monitor
A simulated drone posts events to a memory bus, and an AI module monitors them: a rule detector issues a warning, a monitoring agent diagnoses a failure, a hijacking, or an spoofing and issues an alert, and a reporting agent explains what happened at the end. The website displays everything and allows users to chat with both agents.


## Running it
Requirements: Python 3.12 with `uv`, Node with `pnpm`, and vLLM with `Qwen/Qwen3-14B-AWQ` already in the local Hugging Face cache.

```
tools/vllm/serve.sh start                                  # default profile "actual": Qwen3-14B-AWQ, no reasoning
uv run --project platform python -m platform_app.app       # API + WebSocket on 127.0.0.1:8100
uv run --project ai-module-py python -m ai_module          # detector + agents (no --profile needed)
(cd web && pnpm dev)                                       # web on http://127.0.0.1:3000
tools/vllm/serve.sh stop
```

Everything runs on `127.0.0.1`. On startup the AI module asks vLLM (`GET /v1/models`) which model it serves and stops with an error naming both models and the profile if it is not the one in its configuration.

A whole scenario without the web: `uv run --project platform python -m platform_app.run --scenario demo --speed 16 --wait-agent --evaluate`.

### Model profiles
`model-profiles/<name>.yaml` change the server, the model and the sampling without touching the prompts. `actual` (the default) means the configuration in `agent-assets/agents.yaml`: Qwen3-14B-AWQ, temperature 0 for the monitor and the chats, 0.7 / 0.8 for the report, with all the model aids on. `qwen2.5-14b` is the previous reference model (`tools/vllm/serve.sh start qwen2.5-14b`, and `--profile qwen2.5-14b` in the AI module and in `run.py`). Compare profiles with `tools/experiments/run_matrix.py`.
