# Fase 8 · Liberar al agente, parte A: ejecución y datos (28/10/2026)

Perfil base `qwen3-14b-t0` (determinista, 1 repetición por escenario, seis escenarios). Matrices: `experiments/e8-base/` (B0), `experiments/e8-una/` (seis perfiles, una ayuda apagada cada uno) y `experiments/e8-comb/` (combinación). **Solo datos, sin conclusiones.** Contratos y código de producción sin cambios. No se arrancó ningún modelo híbrido. Todas las ejecuciones terminaron `ok` (la más larga, 145 s), sin cuelgues.

## 1. Paso 0
- **Test** `tests/test_profiles.py::test_think_profiles_raise_max_tokens_and_times`: ahora comprueba `max_invocation_s` del monitor + 15 < `wait_agent_timeout_s` del perfil `qwen3-14b-think` (ya no los valores provisionales 300/90/330). Batería entera: **352 pruebas ok**.
- **Texto quitado** de `agent-assets/prompts/monitor_objective.md` (sección `## raised`, línea que seguía a «If an open alert already explains it…»); la regla del guardrail se queda:
```
  Exception: a `SOURCE_SILENT` detection is always a different fault and gets its own alert (`publish_alert`, without `supersedes`), even if another alert is open.
```
- **Huella nueva de `agent-assets`:** `da0582239a3a3c9a` (en `e72b`: `5627cd4750f82906`).
- **`docs/quien_decide_que.md`:** cabecera puesta al cierre de la 7.2 (modelo `qwen3-14b-t0`) y la fila de la excepción marcada como retirada.
- **B0 (`e8-base`) frente a `e72b`:** mismas etiquetas (A1–A3, F1–F3 ✅), mismas cadenas y causas, 0 abiertas, 0 fallbacks, 0 falsas alarmas, 0 contradicciones, 0 no latinos. **Única diferencia:** `faults` tiene 5 rechazos en vez de 4: aparece uno nuevo en inv-0001 (`checks.link_anomalous = null` frente a `false`, de formato; en e72b no lo hubo), sin efecto en el resultado. B0 vale como base.

## 2. Interruptores
Nombres y valores comprobados en `quien_decide_que.md` §3, `agent/profiles.py` (`AID_KEYS`) y `agents.yaml`: coinciden los seis. Perfiles en `model-profiles/`, idénticos a `qwen3-14b-t0` salvo la clave indicada (bajo `agents.monitor`):

| Perfil | Interruptor |
|---|---|
| `qwen3-14b-t0-sin-coherence-guardrail` | `coherence_guardrail: false` |
| `qwen3-14b-t0-sin-require-checks` | `require_checks: false` |
| `qwen3-14b-t0-sin-computed-facts` | `computed_facts: false` |
| `qwen3-14b-t0-sin-final-tools-only` | `final_iteration_response_tools_only: false` |
| `qwen3-14b-t0-sin-tool-choice` | `tool_choice: auto` |
| `qwen3-14b-t0-sin-silent-own-alert` | `source_silent_own_alert: false` |
| `qwen3-14b-t0-sin-todas-las-sobrantes` | `coherence_guardrail: false`, `final_iteration_response_tools_only: false`, `tool_choice: auto` |

**`require_checks` y el guardrail de coherencia:** `check_coherence` (`guardrails.py`) solo exige `checks` si `require_checks` es verdadero; si `checks` viene y el guardrail está activo, sus valores se comparan igualmente con las tools. Apagar `require_checks` solo deja `checks` opcional en el esquema (`with_optional_checks`) y el guardrail sigue validando los que el modelo escriba. `coherence_guardrail: false` apagado solo: el resto de reglas (`Nothing changes`, `SOURCE_SILENT` propia) sigue activo; en la tabla de rechazos se ve que desaparecen los tipos de formato de `link_anomalous` y de recuperación.

**Paso 2:** ayudas cuyo apagado individual no cambió nada frente a B0 (etiquetas, cadenas, abiertas, fallbacks, falsas alarmas, contradicciones): `coherence_guardrail`, `final_iteration_response_tools_only` y `tool_choice`. Con las tres juntas se ejecutó `e8-comb`. Nota: tras ejecutar las matrices se retocó solo la primera línea (comentario) de los YAML de los perfiles, así que su huella de perfil actual difiere de la de los manifiestos.

## 3. Tablas (seis escenarios sumados; por escenario, `experiments/e8-compare.md` en la carpeta de resultados)
Comparación conjunta hecha juntando los manifiestos de las tres matrices (como en la 7.1). «Cadenas» = etiquetas con exactamente 1 cadena. Rechazos, recordatorios, iteraciones y latencias son del monitor (invocaciones con LLM); tokens de todos los agentes. Por escenario, los demás contadores (no latinos, cortes por longitud) están en el compare.md de cada matriz.

| Perfil | Etiquetas | Cadenas (1 por etiqueta) | Falsas alarmas | Fallbacks | Abiertas | Contradicciones | No latinos | Rechazos (nº) | Recordatorios | Iter. p50/máx | Inv. p50/p95 (s) | Tokens (6 esc.) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `t0` | A1✅ A2✅ A3✅ F1✅ F2✅ F3✅ | 9/9 | 0 | 0 | 0 | 0 | 0 | 14 | 0 | 4/7 | 7.2/12.9 | 502734 |
| `t0-sin-coherence-guardrail` | A1✅ A2✅ A3✅ F1✅ F2✅ F3✅ | 9/9 | 0 | 0 | 0 | 0 | 0 | 8 | 0 | 4/6 | 6.1/9.7 | 477837 |
| `t0-sin-computed-facts` | A1✅ A2✅ A3✅ F1✅ F2✅ F3✅ | 9/9 | 0 | 0 | 0 | 2 | 0 | 47 | 0 | 5/10 | 10.5/19.7 | 666752 |
| `t0-sin-final-tools-only` | A1✅ A2✅ A3✅ F1✅ F2✅ F3✅ | 9/9 | 0 | 0 | 0 | 0 | 0 | 14 | 0 | 4/7 | 7.2/13.2 | 503033 |
| `t0-sin-require-checks` | A1✅ A2✅ A3✅ F1✅ F2✅ F3✅ | 8/9 | 0 | 0 | 0 | 0 | 0 | 14 | 0 | 4/7 | 6.1/13.2 | 515858 |
| `t0-sin-silent-own-alert` | A1✅ A2✅ A3✅ F1✅ F2✅ F3❌ | 9/9 | 0 | 0 | 0 | 0 | 0 | 12 | 0 | 4/5 | 7.2/13.1 | 475241 |
| `t0-sin-tool-choice` | A1✅ A2✅ A3✅ F1✅ F2✅ F3✅ | 9/9 | 0 | 0 | 0 | 0 | 0 | 13 | 0 | 4/6 | 7.1/13.4 | 490173 |
| `t0-sin-todas-las-sobrantes` | A1✅ A2✅ A3✅ F1✅ F2✅ F3✅ | 9/9 | 0 | 0 | 0 | 0 | 0 | 8 | 0 | 4/6 | 6.1/9.6 | 477372 |

| Tipo de rechazo | `t0` | `t0-sin-coherence-guardrail` | `t0-sin-computed-facts` | `t0-sin-final-tools-only` | `t0-sin-require-checks` | `t0-sin-silent-own-alert` | `t0-sin-tool-choice` | `t0-sin-todas-las-sobrantes` |
|---|---|---|---|---|---|---|---|---|
| Nothing changes (decisión) | 4 | 7 | 4 | 4 | 3 | 4 | 4 | 7 |
| SOURCE_SILENT propia (decisión) | 1 | 1 | 1 | 1 | 1 | 0 | 1 | 1 |
| gps_radar_disagreed≠metrics | 0 | 0 | 9 | 0 | 0 | 0 | 0 | 0 |
| link_anomalous null (formato) | 6 | 0 | 5 | 6 | 7 | 5 | 5 | 0 |
| recovery (decisión) | 3 | 0 | 3 | 3 | 3 | 3 | 3 | 0 |
| wind_notable≠metrics | 0 | 0 | 15 | 0 | 0 | 0 | 0 | 0 |
| wind_with_drift≠metrics | 0 | 0 | 10 | 0 | 0 | 0 | 0 | 0 |

Aciertos por etiqueta de cada escenario: demo A1–A3, wind A1, spoofing A1, hijack A1, faults F1–F3; nominal sin etiquetas (0 falsas alarmas en todos). Cortes por longitud: 0 en todos.

## 4. Diferencias frente a B0 por etiqueta
Solo hay diferencias en `faults`; en los otros cinco escenarios los seis perfiles y la combinación coinciden con B0 en etiquetas, cadenas, abiertas, fallbacks, falsas alarmas y contradicciones.

- **`sin-coherence-guardrail`, `sin-final-tools-only`, `sin-tool-choice`, `sin-todas-las-sobrantes`:** ninguna etiqueta cambia. (Cambian contadores sin efecto en el resultado: rechazos, iteraciones, latencia; ver §3.)
- **`sin-require-checks`:** F2 sigue ✅ pero con **2 cadenas y 2 cierres** (en B0, 1). Ejecución `e8-una/runs/qwen3-14b-t0-sin-require-checks/faults/r1`, **inv-0004**: publica una alerta nueva `ai-0004` (`GPS_JAMMING`, sin `supersedes`) donde B0 es rechazado con «Nothing changes… use acknowledge_detection» y reconoce `ai-0003`; esa alerta nueva abre la segunda cadena. También cambian inv-0005 (dos rechazos), inv-0008 (el rechazo cita `ai-0004`) e inv-0010 (2 iteraciones, 0 en B0).
- **`sin-silent-own-alert`:** **F3 pasa de ✅ a ❌** (causa `GPS_JAMMING`, 0 cierres, sin alerta propia). Ejecución `e8-una/runs/qwen3-14b-t0-sin-silent-own-alert/faults/r1`, **inv-0008**: en B0 el guardrail rechaza la respuesta y publica `SENSOR_FAULT`; sin la regla no hay rechazo y el aviso queda dentro de la alerta `GPS_JAMMING` abierta. También cambian inv-0001 (sin el rechazo de `link_anomalous`, 5 iteraciones en vez de 7) e inv-0009.
- **`sin-computed-facts`:** etiquetas ✅ iguales, pero **2 frases que contradicen** los checks (0 en B0), ambas en `faults`: `ai-0001` (inv-0001, «wind … notable but not extreme» con el check de viento notable en no) y `ai-0003` (inv-0003, «Wind is notable and contributes to the drift» con el mismo check en no). Además 34 rechazos de coherencia nuevos (`wind_notable`, `wind_with_drift`, `gps_radar_disagreed` frente a `get_track_metrics`) repartidos en inv-0001, 0003, 0004, 0005, 0006 y 0008; iteraciones p50/máx. 5/10 (4/7 en B0) y tokens +33 %.

## 5. Índice de trazas (para el análisis)
Las trazas de `faults` de B0 y de los tres perfiles con diferencias están en `trazas/fase8/<experimento>_<perfil>_faults_llm_trace.jsonl` de la carpeta de resultados (originales en `experiments/<exp>/runs/<perfil>/faults/r1/llm_trace.jsonl`). Cada invocación es una línea con `invocation_id`.

| Diferencia | Traza | Invocaciones | Traza B0 (mismas invocaciones) |
|---|---|---|---|
| F2: 2 cadenas (`sin-require-checks`) | `e8-una_qwen3-14b-t0-sin-require-checks_faults` | inv-0004, 0005, 0008, 0010 | `e8-base_qwen3-14b-t0_faults` |
| F3 ✅→❌ (`sin-silent-own-alert`) | `e8-una_qwen3-14b-t0-sin-silent-own-alert_faults` | inv-0008 (decisiva), 0001, 0009 | `e8-base_qwen3-14b-t0_faults` |
| Contradicciones y rechazos de coherencia (`sin-computed-facts`) | `e8-una_qwen3-14b-t0-sin-computed-facts_faults` | inv-0001, 0003 (frases); 0004, 0005, 0006, 0008 (rechazos) | `e8-base_qwen3-14b-t0_faults` |

Sin diferencias de resultado (no se incluyen trazas): `sin-coherence-guardrail`, `sin-final-tools-only`, `sin-tool-choice` y `sin-todas-las-sobrantes`.

## 6. Límites
1 repetición por escenario y perfil (temperatura 0): el modelo es determinista salvo el informe (0,7 / 0,8), así que «igual a B0» vale para estos seis vuelos, no mide variabilidad. B0 ya difiere de `e72b` en un rechazo por el cambio de prompt, lo que muestra que cualquier cambio del prompt mueve rechazos aunque el resultado no cambie.

## 7. Mensaje de commit propuesto
```
feat: phase 8 (part A) - one aid off at a time, and combined

- tests: the think-profile test checks the time relation, not provisional values
- agent-assets/prompts/monitor_objective.md: SOURCE_SILENT exception removed
  (it changed nothing; the guardrail rule stays)
- model-profiles: six profiles with one monitor aid off and one with the
  three that changed nothing off
- experiments/e8-base, e8-una and e8-comb: compare.md
- docs: phase 8 data and who-decides-what header updated
```

## 8. Cierre
Servidor parado (`serve.sh stop`), puerto 8000 libre, GPU a 339 MiB (reposo; 0 MiB de vLLM). Instantáneas `snapshots/fase8/` y `snapshots-limpias/fase8/` hechas; las dos comprobaciones de la regla 15 no encuentran nada. Copiados a la carpeta de resultados: `docs/fases/`, `docs/quien_decide_que.md`, los `compare.md` de e8-base, e8-una y e8-comb, la comparación conjunta y las cuatro trazas del índice.
