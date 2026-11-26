# poc-ai-monitor
A simulated drone posts events to an in-memory bus, and an AI module watches them. The **situation monitor** reads the events, estimates the state of the drone (GPS, command link, wind, battery, route…) with decision tables learned from simulated data, and opens, renames and closes **incidents** (a hijack, a GPS spoofing, wind beyond the limit, a silent source…) with the evidence that decided each one. The web shows the drone moving, the events and the incidents, and lets the user look at the rules behind every piece of evidence.

The decision tables are frozen (their hash is checked at start-up); what each state *means* as an incident, when it opens and closes, and how severe it is, is a written policy (`ai-module-py/src/ai_module/situation/policy.yaml`). An assistant that interprets the incidents with an LLM is planned; for now a set of prepared texts plays that role for `demo` and `nominal`.

## Running it
Requirements: Python 3.12 with `uv`, and Node with `pnpm`. Everything runs on `127.0.0.1`; nothing leaves the machine.

```
uv run --project platform python -m platform_app.app                                          # API + WebSocket on 127.0.0.1:8100
uv run --project ai-module-py python -m ai_module.situation --platform http://127.0.0.1:8100  # the situation monitor
(cd web && pnpm dev)                                                                          # web on http://127.0.0.1:3000
```

Start the monitor before pressing Start in the web (or press Reset): it takes the plan of the mission from the bus.

A whole scenario without the web, printing every incident revision:

```
uv run --project platform python -m platform_app.run --scenario demo --speed 16
uv run --project platform python -m platform_app.run --scenario demo --tables handwritten   # the hand-written tables
```

### Options of the monitor
- `--tables learned|handwritten`: the frozen learned tables (default) or the hand-written ones, only to compare them.
- `--assistant scripted|off`: prepared texts for the interpretations, chats and report of `demo` and `nominal`, or none.

### Calibration and training
`tools/situation/calibrate.py` chooses the tracker parameters (k and m) and measures the incidents per type on the simulated variants; `tools/training/` generates the variants, trains the tables and freezes them.

### Model profiles
`model-profiles/<name>.yaml` change the server, the model and the sampling of a local vLLM server without touching the prompts in `agent-assets/` (`tools/vllm/serve.sh start <profile>`). They are kept for the assistant that is planned; the situation monitor does not use an LLM.
