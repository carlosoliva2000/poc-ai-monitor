# poc-ai-monitor
A simulated drone posts events to an in-memory bus, and an AI module watches them. The **situation monitor** reads the events, estimates the state of the drone (GPS, command link, wind, battery, route…) with decision tables learned from simulated data, and opens, renames and closes **incidents** (a hijack, a GPS spoofing, wind beyond the limit, a silent source…) with the evidence that decided each one. The web shows the drone moving, the events and the incidents, and lets the user look at the rules behind every piece of evidence.

The decision tables are frozen (their hash is checked at start-up); what each state *means* as an incident, when it opens and closes, and how severe it is, is a written policy (`ai-module-py/src/ai_module/situation/policy.yaml`). An **LLM assistant** (a local vLLM server) writes the text around the incidents: an interpretation of each update, a hypothesis when the cause is undetermined, the chats, the mission report and, for the instructor, a translator of wind orders and a debriefing. It decides nothing about an incident: its text is marked as its own and every output is checked before it is published.

## Running it
Requirements: Python 3.12 with `uv`, and Node with `pnpm`; the assistant needs a local vLLM server (`tools/vllm/serve.sh start`). Everything runs on `127.0.0.1`; nothing leaves the machine.

```
uv run --project platform python -m platform_app.app                                          # API + WebSocket on 127.0.0.1:8100
uv run --project ai-module-py python -m ai_module.situation --platform http://127.0.0.1:8100  # the situation monitor
uv run --project ai-module-py python -m ai_module.assistant  --platform http://127.0.0.1:8100  # the student's assistant (LLM)
uv run --project ai-module-py python -m ai_module.instructor --platform http://127.0.0.1:8100  # the instructor's assistant (LLM)
(cd web && pnpm dev)                                                                          # web on http://127.0.0.1:3000
```

Start the monitor before pressing Start in the web (or press Reset): it takes the plan of the mission from the bus.

A whole scenario without the web, printing every incident revision (it starts the monitor and the two assistant processes; if vLLM does not answer it says so and goes on with the monitor only, and `--no-llm` leaves the assistant out):

```
uv run --project platform python -m platform_app.run --scenario demo --speed 16
uv run --project platform python -m platform_app.run --scenario demo --tables handwritten   # the hand-written tables
```

### Options of the monitor
- `--tables learned|handwritten`: the frozen learned tables (default) or the hand-written ones, only to compare them.
- `--no-llm` (`platform_app.run`): do not start the assistant. Its prompts are frozen (`agent-assets/prompts_freeze.json`) and its model is `agent-assets/assistant.yaml` (or `POC_LLM_MODEL`).

### Calibration and training
`tools/situation/calibrate.py` chooses the tracker parameters (k and m) and measures the incidents per type on the simulated variants; `tools/training/` generates the variants, trains the tables and freezes them.

### Model profiles
`model-profiles/<name>.yaml` describe a local vLLM server (`tools/vllm/serve.sh start <profile>`; only its `server` section is read: model, tool-call parser, reasoning parser, length, extra arguments, environment). `actual` serves the default model (`Qwen/Qwen3-14B-AWQ`); a profile for another model is copied there and started the same way.
