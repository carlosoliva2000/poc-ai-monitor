# Fase 10 · Consolidación (29/10/2026)

Escrito para: el equipo que revisa la fase (Carlos). Contratos **sin cambios** (`git status` limpio en `contracts/`, `platform/` solo en `run.py`, y la web solo el script de capturas). `agent-assets/` cambia en una línea de `agents.yaml` (modelo, razonamiento y el interruptor nuevo); no se tocan prompts, skills ni `tools.json`. Huella de `agent-assets`: `e41c4a68a68dfa93` (antes `da0582239a3a3c9a`). No se arrancó ningún modelo híbrido.

## Paso 1 · Modelo por defecto
- **`agents.yaml`**: `llm.model: Qwen/Qwen3-14B-AWQ` y `llm.reasoning: false` (se envía `enable_thinking: false` en cada petición). El muestreo ya coincidía con `qwen3-14b-t0` (temperatura 0 en monitor y chats, informe 0,7 / 0,8, `repetition_penalty` 1,05).
- **Perfiles, antes y después**

| Perfil | Antes (Fase 9) | Ahora |
|---|---|---|
| `actual` | Qwen2.5-14B, «`agents.yaml` sin cambios» | Qwen3-14B-AWQ sin razonamiento, «`agents.yaml` sin cambios» (la configuración por defecto) |
| `qwen2.5-14b` | no existía | Qwen2.5-14B-Instruct-AWQ con `reasoning: null` (no se envía `enable_thinking`): la referencia antigua |
| `qwen3-14b-t0` | Qwen3-14B sin razonamiento | igual (queda equivalente a `actual`; se conserva porque los manifiestos de e8 lo citan) |
| `qwen3-14b-t0-sin-hechos-sin-coherencia` | no existía | `computed_facts: false` + `coherence_guardrail: false` (para el paso 4.2) |

- **`serve.sh start` sin perfil** usa `actual` (Qwen3-14B-AWQ, `--reasoning-parser qwen3`, `hermes`, 32768). El README tiene ahora una sección «Running it» con los cuatro comandos y la nota de los perfiles; el `CLAUDE.md` raíz y el del módulo de IA, al día.
- **`qwen2.5-14b` frente a e0e1 (importante para E4):** es **el modelo antiguo con su servidor y su muestreo, pero con las ayudas y los `agent-assets` de hoy** (incluidas `source_silent_own_alert` y `no_duplicate_cause`); **no es una repetición exacta de e0e1** y así se comparará en E4. Comprobado comparando el `profile.json` de `experiments/e0e1/runs/actual/demo/r1` con los parámetros efectivos del perfil nuevo (servidor, modelo y muestreo, razonamiento y tiempos de los cuatro agentes): **idénticos**; solo difieren las ayudas `source_silent_own_alert` (posterior a e0e1) y `no_duplicate_cause` (nueva). `run_matrix.py --profiles qwen2.5-14b --dry-run` imprime ahora el comando de vLLM (`vllm serve Qwen/Qwen2.5-14B-Instruct-AWQ … --tool-call-parser hermes`, sin parser de razonamiento) y los parámetros efectivos de cada agente. Lo mismo para `actual` frente a `qwen3-14b-t0` de e8-base: solo difiere `no_duplicate_cause`.
- **Comprobación del modelo al arrancar** (`agent/llm.py::check_served_model`, llamada desde `__main__.py` si hay agentes): `GET /v1/models` con el SDK `openai` (`models.list()`); si el modelo de la configuración o el perfil no está, o vLLM no responde, para con `error: the LLM server at … serves A but the configuration expects B (profile P) …` o `… does not answer GET /models …`. Con `--detector-only` no se comprueba. `platform_app.run` ya no se queda esperando 20 s si el módulo muere al arrancar: para y enseña sus últimas líneas. Servidor falso: `/v1/models` contesta el modelo de `agents.yaml` o el de `--model` (que `run_matrix --fake` pasa por perfil). Probado también en vivo: el módulo arrancó sin `--profile` contra vLLM con Qwen3-14B y registró `LLM server checked: serves Qwen/Qwen3-14B-AWQ`. Tests (`tests/test_model_check.py`, 7): coincide, no coincide (dice los dos nombres y el perfil), sin perfil, vLLM caído, el módulo para con `SystemExit`, y `--detector-only` no lo exige. ⚠️ Este `openai` (3.35.1) depende de `httpx2`, no de `httpx`: no se importa `httpx` directamente.
- **GPU en reposo y `serve.sh`:** `start` mide la memoria justo antes de cada arranque (antes, solo la primera vez) y `stop` da la GPU por libre cuando `memory.used ≤ reposo + 512 MiB` **y** no queda ningún proceso del grupo de vLLM (`pgrep -g`); sin referencia, solo el margen. No espera 0 MiB. Anotado en el `CLAUDE.md` raíz (la segunda pantalla ocupa ~100–340 MiB aunque vLLM esté parado). Tests nuevos en `test_serve_sh.py`: sin perfil → `actual`; reposo re-medido en cada arranque (340 MiB con la pantalla enchufada, `stop` OK); un proceso superviviente → código 7 «vLLM processes are still alive».
- Los tests existentes que fijaban el muestreo del perfil antiguo se actualizaron (`extra_body` ahora lleva `chat_template_kwargs.enable_thinking: false`; `actual` ya no es «sin interruptor de razonamiento») y se añadió el de `qwen2.5-14b` (no lo envía).

## Paso 2 · Métrica «checks que no cuadran con las tools»
- El monitor guarda en la traza (`InvocationTrace.expected_checks`, por `alert_id`) los valores que debían tener los seis `checks` según las tools y el estado: **los mismos que calcula el guardrail** (`expected_checks` de `guardrails.py`), con el guardrail encendido o apagado y calculados antes de emitir la alerta.
- `evaluate.py` los compara con los declarados en las alertas publicadas por el modelo (sin fallbacks): `eval.md` lleva «· N checks que no cuadran con las tools» en el resumen y una sección con la tabla (alerta, instante, campo, declarado, esperado) y el desglose por campo; una alerta sin `checks` se lista aparte y no cuenta; una ejecución anterior (sin el dato) sale **n/d**. Informativo: «Severidad de las alertas publicadas por etiqueta» (cada alerta con causa, severidad y T+, sin juicio). `eval.json`: `checks_mismatches` y `alert_severities`.
- `compare.md`: columna «Checks≠tools» (suma; n/d si no hay medida) y tabla por campo cuando hay alguna. `compare.py` admite varios experimentos (`python -m ai_module.compare experiments/e10 experiments/e8-base --out …`, los perfiles pasan a `<experimento>/<perfil>`).
- Tests: 7 en `test_evaluate.py` (coinciden = 0, cuenta por campo y alerta, `link_anomalous` nulo, sin checks, fallback, traza antigua = n/d, severidades), 3 en `test_compare.py` y 1 en `test_coherence.py` (la traza guarda lo esperado con el guardrail apagado).

## Paso 3 · Regla de causa duplicada
- `monitor.no_duplicate_cause: true` en `agents.yaml` (`AgentConfig`, `aids()`, `AID_KEYS`, y los nombres de ayudas del informe y de `eval.md`): `publish_alert` **sin `supersedes`** se rechaza si hay una alerta **abierta** con la misma causa: «ai-XXXX (CAUSA) is open: use supersedes ai-XXXX if the cause or severity changes, or acknowledge_detection».
- Solo cuentan las alertas con `status == OPEN` (`state.open_alerts()`): una sustituida pasa a `SUPERSEDED` (`monitor_state.py`), así que solo cuenta la cabeza de cada cadena; una cerrada tampoco. **Exento:** un `SOURCE_SILENT` nuevo (el que `source_silent_own_alert` obliga a publicar como alerta propia, aunque haya una `SENSOR_FAULT` abierta de otra fuente).
- Tests en `test_guardrails.py` (7): duplicado rechazado con el mensaje exacto; con `supersedes` aceptado; causa distinta; cerrada no cuenta; **sustituida no cuenta** (WIND `ai-1` sustituida por `SENSOR_FAULT` `ai-2`, una WIND nueva sin `supersedes` se acepta, y la cabeza `ai-2` sí cuenta); `SOURCE_SILENT` exento; interruptor apagado = comportamiento anterior.

## Paso 4 · Validación
Baterías: `ai-module-py` **390** (360 en la 9.2), `platform` **220**, `contracts` **130** (+1 omitida), `ruff` limpio en los tres. La batería de `ai-module-py` tarda ~3,5 min.

### 4.1 `e10` (perfil `actual`, seis escenarios, 1 repetición) frente a `e8-base`
Comparación conjunta: `experiments/e10-vs-e8-base.md` (juntando manifiestos con `compare.py`). **Sin regresión:**

| | e10 (`actual`) | e8-base (`qwen3-14b-t0`) |
|---|---|---|
| Etiquetas | A1–A3, wind, spoofing, hijack, F1–F3 ✅ | igual |
| Cadenas (1 por etiqueta) | 9/9 | 9/9 |
| Falsas alarmas / fallbacks / abiertas / contradicciones | 0 / 0 / 0 / 0 | 0 / 0 / 0 / 0 |
| Rechazos del monitor (demo, wind, spoofing, hijack, faults) | 3 · 1 · 1 · 1 · 5 | 3 · 1 · 1 · 1 · 5 |
| **Checks≠tools** | **0 en los seis** | n/d (no existía) |
| Tokens prompt de `demo` / `faults` | 135 481 / 190 081 (+42 / +10) | 135 439 / 190 071 |

La regla de causa duplicada **no actuó** (ningún rechazo «is open: use supersedes…» en las trazas de e10), igual que e8-base no tuvo la segunda cadena de F2: la regla no se ha medido en acción con el modelo real (sí con los tests). Latencia de invocación p50/p95 de `demo` 5,4 / 13,9 s (5,3 / 12,7 en e8-base): ruido. Huella de `agent-assets` distinta a la de e8-base por `agents.yaml`.

### 4.2 `e10-metrica` (`qwen3-14b-t0-sin-hechos-sin-coherencia`, solo `faults` ×1)
**La métrica sale distinta de 0: 6 checks que no cuadran** en las 3 alertas publicadas (ai-0001 F1, ai-0003 F2, ai-0008 F3), siempre los mismos dos campos: **`wind_notable` = true y `gps_radar_disagreed` = true declarados, con false esperado** (las tools decían que el viento no es notable y que GPS y radar no discrepan). Las etiquetas siguen ✅ F1–F3 con una cadena cada una, 0 fallbacks y 0 frases que contradicen: **sin la métrica, esta combinación habría parecido igual de buena que B0**, que es lo que la Fase 8 temía. Es el mismo patrón que vio la Fase 8 sin hechos calculados (el modelo declara `true` en esos dos campos sea cual sea el dato). Severidades informativas: F1 SENSOR_FAULT medium, F2 GPS_JAMMING high, F3 SENSOR_FAULT medium.

### 4.3 Demo desde la web con la configuración por defecto
Servicios: `serve.sh start` (sin perfil, 38 s), plataforma, módulo de IA **sin `--profile`** (comprobó el modelo) y web (`pnpm build && pnpm start`); `node scripts/capture.mjs fase10 <carpeta>` (modo nuevo: `demo` a 4× con «esperar al agente», 1920×1080, escala 100 %). Resultado: la demo llegó a «Finished», **4 alertas en la consola** (viento, spoofing con su sustitución por la recuperación, y secuestro; 1 cadena con `supersedes`), informe recibido a los ~205 s de reloj de pared, y los dos chats respondieron (monitor 2,8 s, informe 4,3 s). **No encontré nada de la web que no funcione con el modelo nuevo**; sin errores de página ni de consola. Capturas en `results/capturas/fase10/`: `10`/`11` (viento y con los checks desplegados), `12` (chat del monitor), `20` (spoofing), `21` (recuperación), `30` (secuestro), `40` (informe), `41` (chat del informe), `00`, `01` y `50`.

## Límites y qué queda
- Una repetición a temperatura 0 por escenario: «igual que e8-base» vale para estos seis vuelos, no mide variabilidad. La regla de causa duplicada solo está probada con tests; hace falta un vuelo donde el modelo intente la segunda alerta (F2 con `qwen2.5-14b`, p. ej.).
- `check_served_model` solo comprueba el nombre del modelo, no el parser ni `max_model_len`.
- **Qué queda:** E4 (elegir modelo) con esta configuración y `qwen2.5-14b` como referencia (recordando que no repite e0e1); 3 repeticiones para el Qwen3-30B-A3B-Instruct-2507 (comprobar antes que está en la caché y su parser); decidir si se apaga el guardrail de coherencia ahora que la métrica existe (Fase 8 §4).
- `quien_decide_que.md` y `mejoras_futuras.md` actualizados (cabecera, guardrails, pérdida de GPS, ayudas, evaluación; lo cerrado marcado como hecho).

## Cómo se ejecuta
`tools/vllm/serve.sh start` (perfil `actual`), plataforma, `python -m ai_module` y `pnpm start` en `web/`; matriz: `tools/experiments/run_matrix.py --profiles actual --scenarios demo,nominal,wind,spoofing,hijack,faults --reps 1 --id e10`; comparación: `python -m ai_module.compare experiments/e10 experiments/e8-base --out experiments/e10-vs-e8-base.md`; capturas: `node scripts/capture.mjs fase10 <carpeta>`.

## Revisor de contratos y copias
- **Revisor de contratos** (subagente, solo lectura): sin incumplimientos (separación `ai-module-py`/`platform`, la verdad y las etiquetas solo en `evaluate.py`, textos nuevos en inglés, las siete ayudas coinciden en `agents.yaml`, `AID_KEYS`, `aids()` y los nombres del informe y de `eval.md`). Dos observaciones: el `CLAUDE.md` del módulo decía seis ayudas (**corregido**) y `platform_app/run.py` imprime en castellano algunos mensajes de consola (`[módulo]`, «detecciones abiertas», «error de conexión»; no son de esta fase ni textos para el modelo; **pendiente** si se aplica la regla 14 a rajatabla).
- **Copias:** `docs/fases/` en `results/docs/fases/` (`diff -rq` sin diferencias salvo `quien_decide_que.md`, que solo está allí y en `results/docs/`), `mejoras_futuras.md`, los `compare.md` de e10 y e10-metrica y la comparación conjunta (`experiments/e10-vs-e8-base.md`), `eval.md` e `informe.md` de e10 (`results/runs/e10/<escenario>/`) y el `eval.md` de e10-metrica, y las capturas (`results/capturas/fase10/`, 14). Instantáneas `snapshots/fase10/` (367 ficheros) y `snapshots-limpias/fase10/` (329); los dos `grep` de la regla 15 sobre la limpia: **sin hallazgos**, nada que corregir.

## Servicios al terminar
`serve.sh stop` hecho, puertos 8000, 8100 y 3000 libres y `nvidia-smi` en **0 MiB** (sin la segunda pantalla enchufada en estas pruebas).

## Mensaje de commit propuesto
```
feat: phase 10 - Qwen3-14B as the default model, checks metric and duplicate-cause rule

- agents.yaml: Qwen/Qwen3-14B-AWQ without reasoning; profile "actual" follows it and
  qwen2.5-14b keeps the old reference; serve.sh without a profile uses "actual"
- AI module checks at startup that vLLM serves the configured model; run_matrix
  --dry-run prints the vLLM command and the effective parameters
- serve.sh: idle GPU memory measured at every start; stop compares with it and checks
  that no vLLM process is left (no longer waits for 0 MiB)
- evaluation: "checks that do not match the tools" (eval.md, compare.md, joint
  comparison of several experiments) and alert severities per label
- guardrail: monitor.no_duplicate_cause rejects a new alert with the cause of an open one
- web capture mode fase10; docs and README updated
```
