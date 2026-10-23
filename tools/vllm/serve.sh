#!/usr/bin/env bash
# Arranca y para el servidor vLLM de un perfil de model-profiles/. Un servidor cada vez.
#
#   tools/vllm/serve.sh start <perfil> [--dry-run] [--timeout S]
#   tools/vllm/serve.sh stop [--gpu-timeout S]
#   tools/vllm/serve.sh status
#   tools/vllm/serve.sh gpu-idle        # mide y guarda la memoria de GPU en reposo
#
# Solo toca el proceso que ha lanzado él (su PID está en runs/_servers/vllm.pid): si el puerto
# está ocupado por otro servidor, avisa y sale sin matar nada. Salidas: 0 bien · 2 perfil o
# modelo no válido · 3 puerto ocupado por un servidor ajeno · 4 modelo sin descargar · 5 el
# servidor murió al arrancar · 6 el servidor no avanza · 7 la GPU no se libera · 8 uso incorrecto.
#
# Variables (para pruebas): VLLM_BIN, SERVE_PORT, SERVE_STATE_DIR, HF_CACHE, NVIDIA_SMI,
# GPU_MARGIN_MIB, GPU_TIMEOUT_S, START_TIMEOUT_S, STALL_S, MODEL_PROFILES_DIR.
set -u

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PORT="${SERVE_PORT:-8000}"
STATE="${SERVE_STATE_DIR:-$ROOT/runs/_servers}"
VLLM_BIN="${VLLM_BIN:-$HOME/vllm/bin/vllm}"
HF_CACHE="${HF_CACHE:-$HOME/.cache/huggingface/hub}"
NVIDIA_SMI="${NVIDIA_SMI:-nvidia-smi}"
GPU_MARGIN_MIB="${GPU_MARGIN_MIB:-512}"
GPU_TIMEOUT_S="${GPU_TIMEOUT_S:-120}"
START_TIMEOUT_S="${START_TIMEOUT_S:-900}"
STALL_S="${STALL_S:-300}"
PROFILES=(uv run --project "$ROOT/ai-module-py" python -m ai_module.agent.profiles)
PROFILES_DIR_ARGS=()
[ -n "${MODEL_PROFILES_DIR:-}" ] && PROFILES_DIR_ARGS=(--dir "$MODEL_PROFILES_DIR")
PIDFILE="$STATE/vllm.pid"
PROFILEFILE="$STATE/vllm.profile"
IDLEFILE="$STATE/gpu_idle_mib"

log() { echo "[serve] $*"; }
die() { local code="$1"; shift; echo "[serve] ERROR: $*" >&2; exit "$code"; }

port_busy() { ss -ltn 2>/dev/null | awk '{print $4}' | grep -qE "[:.]${PORT}$"; }
healthy() { curl -sf -m 2 "http://127.0.0.1:$PORT/health" >/dev/null 2>&1; }

# ¿Es nuestro el servidor? PID guardado, vivo y que sea de vllm.
our_pid() {
  [ -f "$PIDFILE" ] || return 1
  local pid; pid="$(cat "$PIDFILE")"
  [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null && tr '\0' ' ' < "/proc/$pid/cmdline" 2>/dev/null | grep -q "vllm" || return 1
  echo "$pid"
}

gpu_used() {
  "$NVIDIA_SMI" --query-gpu=memory.used --format=csv,noheader,nounits 2>/dev/null | head -1 | tr -d ' '
}

measure_idle() {
  mkdir -p "$STATE"
  local used; used="$(gpu_used)"
  [ -n "$used" ] || die 7 "nvidia-smi does not report memory.used"
  echo "$used" > "$IDLEFILE"
  log "GPU idle memory: ${used} MiB (saved in $IDLEFILE)"
}

# Espera a que memory.used vuelva al reposo medido más un margen. En WSL, --query-compute-apps
# puede salir vacío aunque haya procesos en la GPU: solo se anota.
wait_gpu_free() {
  local timeout="$1"
  [ -f "$IDLEFILE" ] || { log "no GPU idle reference: not waiting for the GPU"; return 0; }
  local limit=$(( $(cat "$IDLEFILE") + GPU_MARGIN_MIB )) waited=0 used
  while :; do
    used="$(gpu_used)"
    if [ -n "$used" ] && [ "${used%.*}" -le "$limit" ]; then
      log "GPU free: ${used} MiB <= ${limit} MiB"
      return 0
    fi
    [ "$waited" -ge "$timeout" ] && break
    sleep 2; waited=$(( waited + 2 ))
  done
  log "compute apps: $("$NVIDIA_SMI" --query-compute-apps=pid,used_memory --format=csv,noheader 2>&1 | tr '\n' ';')"
  die 7 "the GPU is not free after ${timeout} s (${used:-?} MiB used, limit ${limit} MiB)"
}

cmd_start() {
  local profile="${1:-}"; shift || true
  local dry=0 timeout="$START_TIMEOUT_S"
  [ -n "$profile" ] || die 8 "usage: serve.sh start <profile> [--dry-run] [--timeout S]"
  while [ $# -gt 0 ]; do
    case "$1" in
      --dry-run) dry=1; shift;;
      --timeout) timeout="${2:?missing value}"; shift 2;;
      *) die 8 "unknown argument: $1";;
    esac
  done

  local model args
  model="$("${PROFILES[@]}" model "$profile" "${PROFILES_DIR_ARGS[@]}")" || die 2 "invalid profile '$profile'"
  args="$("${PROFILES[@]}" serve-args "$profile" --port "$PORT" "${PROFILES_DIR_ARGS[@]}")" || die 2 "invalid profile '$profile'"
  case "$(echo "$model" | tr 'A-Z' 'a-z')" in
    *qwen3.5-27b*|*qwen3.8-27b*) die 2 "model $model is forbidden";;
  esac

  # El modelo tiene que estar en la caché: sin red (HF_HUB_OFFLINE=1).
  local cache_dir="$HF_CACHE/models--${model//\//--}/snapshots"
  if [ ! -d "$cache_dir" ] || [ -z "$(ls -A "$cache_dir" 2>/dev/null)" ]; then
    die 4 "model $model is not in the Hugging Face cache ($cache_dir): ask before downloading it"
  fi

  if port_busy; then
    if pid="$(our_pid)"; then
      if [ "$(cat "$PROFILEFILE" 2>/dev/null)" = "$profile" ] && healthy; then
        log "server of profile $profile already running (PID $pid)"; exit 0
      fi
      die 3 "my server (PID $pid, profile $(cat "$PROFILEFILE" 2>/dev/null)) is running: stop it first"
    fi
    die 3 "port $PORT is in use by a server I did not launch: not touching it"
  fi

  [ -x "$VLLM_BIN" ] || command -v "$VLLM_BIN" >/dev/null || die 2 "vllm not found at $VLLM_BIN"
  # Comprobación previa: que este vLLM conozca cada flag y el parser.
  local help; help="$("$VLLM_BIN" serve --help=all 2>&1)"
  local flag
  for flag in --tool-call-parser --max-model-len --enable-auto-tool-choice $(echo "$args" | grep -o -- '--reasoning-parser'); do
    echo "$help" | grep -q -- "$flag" || die 2 "this vLLM does not know the flag $flag"
  done
  local tool; tool="$(echo "$args" | sed -E 's/.*--tool-call-parser ([^ ]+).*/\1/')"
  echo "$help" | grep -- '--tool-call-parser' | grep -qE "[{,]${tool}[,}]" || die 2 "parser '$tool' not in --tool-call-parser"

  log "profile: $profile · model: $model"
  log "command: HF_HUB_OFFLINE=1 VLLM_USE_FLASHINFER_SAMPLER=0 $VLLM_BIN $args"
  [ "$dry" = 1 ] && { log "(dry-run: nothing is started)"; exit 0; }

  mkdir -p "$STATE"
  [ -f "$IDLEFILE" ] || measure_idle
  local stamp logfile; stamp="$(date +%Y%m%d-%H%M%S)"; logfile="$STATE/${stamp}_${profile}.log"
  export HF_HUB_OFFLINE=1 VLLM_USE_FLASHINFER_SAMPLER=0
  local t0; t0="$(date +%s)"
  # shellcheck disable=SC2086
  eval "set -- $args"
  setsid "$VLLM_BIN" "$@" > "$logfile" 2>&1 < /dev/null &
  local pid=$!
  echo "$pid" > "$PIDFILE"; echo "$profile" > "$PROFILEFILE"
  log "started PID $pid, log $logfile"

  local last_size=-1 last_change="$t0" now size
  while ! healthy; do
    if ! kill -0 "$pid" 2>/dev/null; then
      tail -n 60 "$logfile"; rm -f "$PIDFILE" "$PROFILEFILE"
      die 5 "the server died while starting (last 60 lines above)"
    fi
    now="$(date +%s)"
    size="$(stat -c %s "$logfile")"
    [ "$size" != "$last_size" ] && { last_size="$size"; last_change="$now"; }
    if [ $(( now - last_change )) -ge "$STALL_S" ] || [ $(( now - t0 )) -ge "$timeout" ]; then
      tail -n 60 "$logfile"
      log "stopping my server (no progress / timeout)"
      cmd_stop --quiet-gpu
      die 6 "the server did not reach /health (stalled ${STALL_S} s or total ${timeout} s)"
    fi
    sleep 1
  done
  local secs=$(( $(date +%s) - t0 ))
  local version; version="$(curl -sf -m 3 "http://127.0.0.1:$PORT/version" || echo '{}')"
  printf '{"profile":"%s","model":"%s","pid":%s,"seconds_to_health":%s,"version":%s,"log":"%s"}\n' \
    "$profile" "$model" "$pid" "$secs" "$version" "$logfile" > "$STATE/${stamp}_${profile}.json"
  log "ready in ${secs} s at http://127.0.0.1:$PORT/v1 (version: $version)"
  log "nvidia-smi compute-apps: $("$NVIDIA_SMI" --query-compute-apps=pid,used_memory --format=csv,noheader 2>&1 | tr '\n' ';') · memory.used: $(gpu_used) MiB"
}

cmd_stop() {
  local gpu_timeout="$GPU_TIMEOUT_S" skip_gpu=0
  while [ $# -gt 0 ]; do
    case "$1" in
      --gpu-timeout) gpu_timeout="${2:?missing value}"; shift 2;;
      --quiet-gpu) skip_gpu=1; shift;;
      *) die 8 "unknown argument: $1";;
    esac
  done
  local pid
  if ! pid="$(our_pid)"; then
    if port_busy; then die 3 "port $PORT is in use by a server I did not launch: not touching it"; fi
    rm -f "$PIDFILE" "$PROFILEFILE"
    log "no server of mine is running"
    return 0
  fi
  local pgid; pgid="$(ps -o pgid= -p "$pid" | tr -d ' ')"
  log "stopping PID $pid"
  if [ "$pgid" = "$pid" ]; then kill -TERM -- "-$pid" 2>/dev/null; else kill -TERM "$pid" 2>/dev/null; fi
  local waited=0
  while kill -0 "$pid" 2>/dev/null && [ "$waited" -lt 60 ]; do sleep 1; waited=$(( waited + 1 )); done
  if kill -0 "$pid" 2>/dev/null; then
    log "still alive after 60 s: SIGKILL to my process group"
    if [ "$pgid" = "$pid" ]; then kill -KILL -- "-$pid" 2>/dev/null; else kill -KILL "$pid" 2>/dev/null; fi
    sleep 2
  fi
  rm -f "$PIDFILE" "$PROFILEFILE"
  log "server stopped"
  [ "$skip_gpu" = 1 ] || wait_gpu_free "$gpu_timeout"
}

cmd_status() {
  local pid
  if pid="$(our_pid)"; then
    log "my server is running: PID $pid, profile $(cat "$PROFILEFILE" 2>/dev/null), health: $(healthy && echo ok || echo no)"
  elif port_busy; then
    log "port $PORT is in use by a server I did not launch"
  else
    log "no server running (port $PORT free)"
  fi
  log "GPU memory.used: $(gpu_used) MiB (idle reference: $(cat "$IDLEFILE" 2>/dev/null || echo n/a))"
}

case "${1:-}" in
  start) shift; cmd_start "$@";;
  stop) shift; cmd_stop "$@";;
  status) cmd_status;;
  gpu-idle) pid=""; if our_pid >/dev/null || port_busy; then die 3 "a server is running: the idle memory cannot be measured"; fi; measure_idle;;
  *) die 8 "usage: serve.sh start <profile> | stop | status | gpu-idle";;
esac
