# E7d · Asistente LLM

Informe de cierre. Referencia: especificación del núcleo v2 (v1.3). Escrito para: Carlos, que revisa la fase y hace el commit.

## Qué se hizo
El asistente con textos preparados del vídeo se sustituye por un **asistente LLM** que no decide nada del incidente: solo escribe texto marcado como suyo. Son **dos procesos aparte** (más el monitor, que no cambia): `ai_module.assistant` (alumno) y `ai_module.instructor` (instructor). Todo pasa por el bus; ninguno habla HTTP con la plataforma. El modelo es `Qwen/Qwen3-14B-AWQ` sin razonamiento, temperatura 0 en todos los papeles (también el informe), vLLM local.

## Papeles y qué recibe cada uno
| Papel (proceso) | Qué escribe | Qué recibe |
|---|---|---|
| `explain` (alumno) | Una interpretación (≤ 3 frases, ≤ 60 palabras) de cada revisión `opened`, `renamed`, `state` y `closed` → `IncidentEnriched` | La revisión traducida con `agent-assets/glossary.yaml` (evidencias en inglés llano, **sin umbrales de las filas**), contexto, qué comprobar, los **hechos de ahora** calculados con lo que llegó del bus (distancia GPS–radar, distancia del radar y del GPS a la ruta, viento de la estación con de dónde viene y adónde empuja, viento estimado, C/N0 y AGC frente a su nominal, modo, enlace **con su antigüedad**, batería, telemetría callada) y, aparte, la evidencia **de la apertura** |
| `hypothesis` (alumno) | Solo en un `UNDETERMINED` que se abre, con la tool `propose_hypothesis` | Lo mismo; la causa «posible» de las tablas va como «pista débil que puede ser errónea» |
| `chat` (alumno, `monitor` y `report`) | Respuesta ≤ 5 frases, sin tools | El código pone en el prompt: los incidentes con **su historia con horas** («opened as X at T+…; renamed to Y at T+…; recovering…; closed…»), la severidad máxima que alcanzó cada uno y su orden (calculado por el código), las notas ya publicadas, los hechos de ahora **de cuando se preguntó** (copia del almacén) y la conversación |
| `report` (alumno) | Resumen, una nota por incidente y ≤ 3 recomendaciones (tool `write_report`) | Los incidentes con sus hechos; **los hechos del informe los escribe el código** (cabecera, historia con horas, severidad, confianza, mayor distancia del radar a la ruta mientras estuvo abierto) |
| `translator` (instructor) | Una de tres tools: `propose_wind`, `propose_cancel_wind`, `not_an_order` | La frase y el viento del instructor activo, sacado de los `InstructorCommand` del bus |
| `chat_instructor` (instructor) | Como el chat, **con la verdad** | Lo anterior más lo programado, los fallos, los comandos y la comparación con lo detectado, que escribe el código |
| `debrief` (instructor) | Resumen y ≤ 3 puntos (tool `write_debrief`) | La lista de lo inyectado frente a lo detectado y los retrasos, escrita por el código |

**La verdad solo llega al instructor.** Cinco barreras con test: (1) la verdad vive solo en el proceso del instructor; (2) las suscripciones del alumno no incluyen `sim.*` (salvo el ciclo de vida), `ops.instructor` ni `ai.instructor`; (3) el alumno no importa ningún cliente HTTP (comprobado por imports); (4) el alumno descarta el nombre del escenario (solo guarda el `run_id`) y su almacén tira lo que no es suyo aunque llegue; (5) lo del instructor sale por `ai.instructor`, que el alumno no recibe y la vista del alumno de la web filtra. Un test central pasa un flujo con fallos, órdenes, `ExerciseInjects` y mensajes del instructor y comprueba con un LLM falso que ningún prompt del alumno lleva nada de eso.

## Qué revisiones se interpretan y la cola
Se interpretan `opened`, `renamed`, `state` y `closed` (`severity` es política y `evidence` ya se ve en la tarjeta). Una plaza de LLM por proceso con prioridad (aperturas e hipótesis > recuperaciones > chats > cierres > informe); una revisión más nueva del mismo incidente sustituye a la pendiente y cancela la de curso; una interpretación que no ha empezado a los 10 s se descarta; un reintento solo si no han pasado 8 s. **Plazo de la web: 10 s** para todos los tipos (`max(10 s, 2 × p90)`, medido), «pending…» hasta entonces y «No interpretation: the assistant did not answer in time» después (un texto tardío se enseña igualmente). Con `--no-llm` las tarjetas dicen eso mismo pasados 10 s.

## Qué se comprueba de la salida (`assistant/checks.py`)
Normaliza U+2011 y espacios raros; rechaza: ids (`gps-…`, `inc-…`, `GI-02`), nombres internos (`GPS_SPOOFING`, `snake_case`), **cifras y horas que no estaban en la entrada** (con la tolerancia de su redondeo), una cifra que solo existe en la apertura dicha como de ahora («now», «currently», «is»), **una causa que el incidente no dice** (léxico por causa, también «X was the cause»; aunque la frase aparezca en la entrada: las evidencias pueden traer una causa contraria; sí vale el vocabulario del propio «qué comprobar» y lo que el operador preguntó), idioma (CJK o castellano) y longitud. Un reintento con los motivos; si vuelve a fallar: la interpretación no se publica, el chat da un texto fijo y el informe sale con los hechos y esas frases marcadas como no disponibles.

## Medidas (fuera de línea, una llamada cada vez, 119 interpretaciones de `demo`, `nominal` y 20 variantes; `experiments/e7d/paso6-final-medidas.md`)
- **Latencia por llamada:** explicar, mediana 0,7 s y p90 0,8 s; hipótesis, mediana 4,6 s y p90 5,0 s. Chats en directo: mediana ≈ 1–2 s, máximo 3 s. Informe y debriefing, 3–5 s tras el fin.
- **Se publican** 108 de 110 explicaciones y 9 de 9 hipótesis. Rechazos por motivo (todos los intentos): longitud 10, causa 5, cifra 2, «ahora frente a la apertura» 1 (por «now»; **ninguno por «is»**, así que la regla se queda como estaba). Ningún error del LLM.
- **En directo** (monitor, los dos procesos y la web; `demo` y `nominal` con `capture.mjs`): todos los textos llegaron antes de 2 s, ninguno cayó en el plazo, 0 errores del bus.

## Textos con la verdad al lado
`experiments/e7d/paso6-final-textos.md` (cada revisión con el texto, la verdad en ese instante y lo programado; copiado a `results/`). Revisados con la rúbrica, los defectos que **las comprobaciones no ven**: una tendencia que no está en los datos («wind remains above the limit but is decreasing»), especulación («the drone's behavior suggests a possible hijack… unauthorized access»), «the cause is not known» en un secuestro en recuperación, «below the normal level at opening» mal usado y un «strong wind» inventado en un failsafe. Lo que sí se ve distinto del vídeo: el texto cita cifras reales del caso (79 m, 261 m, 1,5 veces el límite).

### Hipótesis (formato y medida)
Formato (contrato v1.4): `kind` (la primera), `confidence: possible`, `evidence_event_ids` (los de la revisión, los pone el código), `ranked` (≤ 3 causas de WIND, GPS_SPOOFING, HIJACK, DEAD_RECKONING, cada una con `supports` y `missing`) y `checks` (≤ 4, con `target` de lista cerrada). La E8 puede medir si la primera acierta (frente a `drone.cause`) y si los `checks` incluyen la fuente que distingue la causa.
- **Casos reales** (9 «sin determinar», 4 de validación y 5 de generalización; 7 eran viento de verdad y 1 falsa alarma): la primera fue WIND en 5 de 8.
- **Aproximación fuera de línea** (`paso6-hipotesis-aprox.md`, **aparte y marcada como aproximación**: causa conocida con todo lo que la nombra quitado de la entrada; optimista en secuestro y estima, porque los hechos de ahora los delatan): la primera acierta en **32 de 40 (80 %)**: secuestro 10/10, estima 10/10, viento 10/10, **engaño 2/10**. El prompt de la hipótesis se ajustó tres veces con la misma muestra de validación (hay un balancín viento/engaño) y **queda congelado**; el engaño va a la E8, que lo medirá con el reservado.

## Traductor de órdenes
Catálogo: `set_wind` y `cancel_wind` (lo que la plataforma sabe aplicar). El LLM llama a `propose_wind` con el rumbo, la **velocidad y su unidad tal como se dijeron** (cifra o palabra: «20», «twenty»; m/s, knots, km/h, mph); **el código** convierte el rumbo a grados y las unidades a m/s (y lo dice: «Converted by the assistant: 20 knots = 10.3 m/s»), comprueba que la velocidad y la unidad estaban en la frase (con «wind from the south» el modelo rellenaba un 0), valida los rangos de la plataforma, rellena rampa y duración diciéndolo y escribe el texto de la propuesta. Una velocidad en cifras por encima de 40 m/s (tras convertir) se rechaza sin llamar al modelo. Ambigua → una pregunta; sin velocidad → «What speed, in m/s?»; fuera del catálogo → «From this chat I can only propose wind»; Beaufort → pide m/s; «Remove the wind» sin viento activo (según los comandos del bus) → lo dice. **Nunca publica `InstructorCommand`**: la web manda el comando al pulsar Confirm (solo con el modo interactivo). Ejemplos reales en `experiments/e7d/paso4-ejemplos.md` y capturas `video2/08–11`.

## Lo retirado (lista aprobada) y lo que arrastró
- **A:** `situation/scripted.py`, `scripted_texts.yaml`, la clave `assistant` de `config.yaml`, `--assistant` del monitor y de `platform_app.run`, y sus tests (`test_monitor_chat_and_report_texts`, `test_scripted_assistant_publishes_like_the_llm` y, **no previsto en la lista**, `test_instructor_script_gives_its_two_proposals`, que dependía del módulo borrado).
- **B:** `ai_module/agent/` (`profiles.py` y `__init__.py`); sustituido por `tools/vllm/serve_args.py` (solo lee la sección `server`; **ignora el resto**, así que un perfil archivado se copia de vuelta y `serve.sh` lo arranca; test con un perfil de otro modelo, parser `mistral`).
- **C:** 22 ficheros de `agent-assets/` (`agents.yaml`, `tools.json`, 16 prompts y las 4 skills).
- **D:** 31 perfiles de `model-profiles/` (queda `actual.yaml`), **archivados con un README** en `~/poc-backups/model-profiles-archivo/`.
- **F (los 8 eventos del módulo anterior) y la dependencia `openai`:** se quedan (los usa el asistente; los eventos, hasta la D1).

## Contrato v1.4 (aditivo)
`IncidentHypothesis.ranked` y `.checks` (con los validadores: la primera es `kind`, sin repetir, solo las cuatro causas, `target` de lista cerrada); `IncidentEnriched.model` y `.prompt_sha`; `ExerciseInjects` (`inj-`, `sim.instructor`, de `labels.json`, lo publica la plataforma tras `SimulationStarted`); `DebriefGenerated` (`ai.instructor`, `ai-debrief`; en lugar de `ReportGenerated.audience`, que habría mezclado lo del instructor con lo del alumno); nombres de agente `assistant`, `translator` y `debrief`. Documento, modelos, 51 esquemas, ejemplos (`test_doc_examples`) y `web/lib/contracts.ts` juntos. **Ids con etiqueta de proceso** (v1.4, el formato admite una letra minúscula tras el prefijo: `<prefijo>(-<letra>)?-<número>`, de modo que `ai-0001` sigue valiendo): monitor `ai-m-0001`, asistente del alumno `ai-a-0001`, del instructor `ai-i-0001`, y lo mismo con `act-` y `chk-`; `inc-` e `inv-` no se comparten. Ver «Problemas».

## Configuración y huella
`agent-assets/assistant.yaml` (modelo, cola y una entrada por papel: prompt, tools, `temperature`, `top_p`, `max_tokens`, `timeout_s`, `enabled`); `POC_LLM_MODEL` pisa el modelo. **Los prompts están congelados** (`agent-assets/prompts_freeze.json`: prompts, esquemas de tools, glosario y `assistant.yaml`; sha 12 hex en cada `IncidentEnriched.prompt_sha`): los procesos no arrancan si algo cambió y `test_prompts_freeze` lo vigila; se refresca con `tools/assistant/freeze_prompts.py`. `platform_app.run` arranca monitor y asistente por defecto; si vLLM no responde (o un proceso del asistente no arranca) **lo dice y sigue solo con el monitor** (`--no-llm` para no arrancarlo).

## Tests
Módulo de IA **235** (nuevos: `test_assistant`, `test_instructor`, `test_report`, `test_prompts_freeze`, `test_e2e_platform` y los de `serve.sh` con perfil de ejemplo), plataforma **303**, contratos **139**, web **85**. `ruff check` limpio; `ruff format --check` solo marca `tools/e7a_gnss_example.py`, que no he tocado. `pnpm typecheck` bien; `pnpm build` falló la primera vez (`exitCode: 1`) y pasó la segunda, como en la E7c. Lo congelado (`features.py`, tablas, regla, catálogo, seguidor, política, `tables_freeze.json`) sin cambios (`check_freeze` ok) y `runs/<escenario>/` sin cambios.

## Problemas
- **Ids repetidos (encontrado en el ensayo con la web):** los tres procesos numeraban `ai-0001…` y la plataforma rechazaba los textos del asistente («an event with id … already exists»). Ninguna prueba lo vio y **mis medidas de los pasos 2 a 4 leían las trazas, que se escriben antes de publicar**: la latencia de generación vale, pero lo que dije de que los textos «llegaban» no estaba comprobado entonces (en el paso 3 el streaming sí llegaba, por tener ids propios). Corregido primero con rangos de ids (`ai-1001…`) y, **en la revisión, con una etiqueta de proceso en el id** (`ai-m-`, `ai-a-`, `ai-i-`), porque los rangos chocaban en cuanto un proceso pasara de 1000 eventos (un ejercicio largo, varios drones en la D1): el formato del contrato lo admite sin romper (se relajó el validador `matches_id_prefix`; los ids sin etiqueta siguen valiendo) y hay un test que numera 2500 ids por proceso y prefijo sin colisión. Un **test extremo a extremo con la plataforma real** (`test_e2e_platform`, comprobado que falla sin el arreglo) cubre el bus compartido; el ensayo de `demo` y `nominal` con la web se hizo con los rangos y no se ha repetido (solo cambia el formato del id).
- `pnpm dev` paró con el aviso de seguridad de Next.js 16.4.1 la primera vez (ya anotado); no se actualiza.
- Un `pkill` con un patrón que coincidía con mi propia orden me mató el shell dos veces; los procesos se paran por PID.
- **Instantáneas (reglas 13 y 15):** `snapshots/e7d/` con 645 ficheros y `snapshots-limpias/e7d/` con 589; las dos búsquedas de la regla 15 salieron vacías a la primera. El `cp` avisa de los ficheros borrados que git aún tiene en el índice (los de la lista aprobada, sin commitear): es esperado.
- Nada que haya pasado de 30 minutos.

## Lo que propongo cambiar en la especificación
- **§7:** el traductor comparte proceso con el chat del instructor y el debriefing (proceso del instructor); el asistente del alumno es otro proceso, sin acceso a la verdad. La verdad entra por `ExerciseInjects` (más los fallos y comandos), y el debriefing es `DebriefGenerated` en `ai.instructor`.
- **§7:** el plazo de la web es único, **10 s**, medido (interpretaciones ≤ 1,7 s, hipótesis ≈ 5 s).
- **§7:** la dependencia `openai` se queda (la usa el asistente).
- **Temperatura 0 también en el informe** (regla 6 del `CLAUDE.md` cambiada).
- **§2:** una regla más de conexión: los procesos del módulo que comparten bus llevan una etiqueta de proceso en los ids de los prefijos compartidos (`ai-a-0001`).
- **§8 (E8):** medir el asistente a ciegas con la rúbrica, la primera hipótesis (hoy, aproximación 32/40, engaño 2/10) y su «qué comprobar»; lista de fallos de texto que las comprobaciones no ven en `docs/mejoras_futuras.md`.
- **§12:** v1.4 (aditiva), E7d cerrada.

## URLs consultadas
Ninguna: no he afirmado nada nuevo sobre librerías.

## Mensaje de commit propuesto
```
E7d: LLM assistant (student and instructor processes), contract v1.4, retire the scripted assistant

- assistant (student): explains each incident revision, proposes a marked hypothesis for undetermined
  deviations, answers the monitor and report chats and writes the mission report; the code writes
  the facts (histories with times, figures) and checks every output before publishing it
- instructor process: order translator (the LLM only picks a tool; the code converts bearing and
  units, validates ranges and never applies anything), chat and debriefing with the truth of the
  exercise; the student process never receives it
- contract v1.4 (additive): structured hypothesis, ExerciseInjects, DebriefGenerated, model and
  prompt sha in IncidentEnriched, a per-process tag in shared ids (ai-m-, ai-a-, ai-i-; a shared bus rejects repeated ids)
- one LLM slot per process with priority, replacement and expiry; single 10 s web deadline
- frozen prompts (sha checked at start-up); platform_app.run starts the assistant by default and
  says so if vLLM is down (--no-llm)
- retire the scripted assistant, ai_module/agent, the old agent-assets and 31 model profiles
  (archived outside the repo); serve_args.py reads only the server section of a profile
- end-to-end test against the real platform bus; web: debriefing for the instructor view
```
