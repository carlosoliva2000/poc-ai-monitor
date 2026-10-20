#!/bin/bash
# Hook de Claude Code para el Python de la PoC (adaptado de ~/spike1/py/hook_py.sh). Se registra en
# PostToolUse (Write|Edit|Bash) y en Stop. Solo toca los ficheros que han cambiado: el .py que acaba
# de escribir Write/Edit y, para cualquier evento (también Bash y Stop), los .py de contracts/python,
# platform y ai-module-py modificados desde la última comprobación correcta (marca de tiempo
# .tools/format.stamp). Cada fichero pasa por `ruff check --fix` (solo arreglos seguros: imports
# ordenados, sin usar...) y por `ruff format`; después `ruff check` sin arreglos. Si queda alguna
# violación (p. ej. una línea de más de 100 columnas que el formateador no puede partir) sale con
# código 2 y las violaciones por stderr (Claude las ve y las corrige) y la marca no avanza, así que
# el fallo se vuelve a avisar hasta que se arregle. Un Stop que ya viene de un aviso previo
# (stop_hook_active) no vuelve a bloquear: avisa al usuario y termina. Cada ejecución deja una línea
# en .tools/hook.log.
root="$(cd "$(dirname "$0")/.." && pwd)"
stamp="$root/.tools/format.stamp"
mkdir -p "$root/.tools"
[ -e "$stamp" ] || touch "$stamp"

ruff="$(command -v ruff || echo "$HOME/.local/bin/ruff")"
if [ ! -x "$ruff" ]; then
  echo "ruff no está instalado (uv tool install ruff)" >&2
  exit 2
fi

{
  read -r event
  read -r explicit
  read -r active
} < <(python3 -c '
import json, sys
data = json.load(sys.stdin)
response = data.get("tool_response")
path = response.get("filePath") if isinstance(response, dict) else None
path = path or data.get("tool_input", {}).get("file_path") or "-"
print(data.get("hook_event_name", "?")); print(path); print(data.get("stop_hook_active", False))
')

roots=("$root/contracts/python" "$root/platform" "$root/ai-module-py")
files=()
case "$explicit" in
  "$root"/contracts/python/*.py | "$root"/platform/*.py | "$root"/ai-module-py/*.py)
    case "$explicit" in */.venv/*) ;; *) [ -f "$explicit" ] && files+=("$explicit") ;; esac ;;
esac
while IFS= read -r changed; do
  files+=("$changed")
done < <(find "${roots[@]}" -name '*.py' -newer "$stamp" -not -path '*/.venv/*' \
  -not -path '*/__pycache__/*' 2> /dev/null)
if [ ${#files[@]} -gt 0 ]; then
  mapfile -t files < <(printf '%s\n' "${files[@]}" | sort -u)
fi

echo "$(date '+%F %T') $event: ${files[*]:-sin ficheros Python cambiados}" | sed "s#$root/##g" >> "$root/.tools/hook.log"
[ ${#files[@]} -eq 0 ] && exit 0

cd "$root" || exit 1
"$ruff" check --fix --quiet "${files[@]}" > /dev/null 2>&1
if ! formatted=$("$ruff" format "${files[@]}" 2>&1); then
  echo "ruff format no pudo formatear los ficheros:" >&2
  echo "$formatted" >&2
  exit 2
fi
violations=$("$ruff" check --output-format concise --no-fix "${files[@]}" 2>&1 | grep -E "^[^ ]+:[0-9]+:[0-9]+:")
if [ -n "$violations" ]; then
  if [ "$event" = "Stop" ] && [ "$active" = "True" ]; then
    python3 -c 'import json, sys; print(json.dumps({"systemMessage": "ruff sigue fallando en el Python:\n" + sys.argv[1]}))' "$violations"
    exit 0
  fi
  echo "ruff falla en el Python de la PoC (corrígelo antes de seguir):" >&2
  echo "$violations" >&2
  exit 2
fi
touch "$stamp"
exit 0
