# Comparativa nivel 0 (carga) · 23/10/2026

Todos con `--max-model-len 32768`, `VLLM_USE_FLASHINFER_SAMPLER=0`, vLLM 0.31.0 y GPU de 24463 MiB. Datos de `nivel0_<clave>.md` y `logs/`. «Tiempo hasta /health» incluye la descarga del modelo en la primera ejecución (actual ya estaba en caché; los demás, no).

| Candidato | Veredicto | Hasta /health | Memoria GPU cargado | Caché KV (tokens; concurrencia 32k) | Muestreo heredado (generation_config.json) | Campo de razonamiento | Avisos |
|---|---|---|---|---|---|---|---|
| actual (Qwen2.5-14B-AWQ) | PASA | 62,1 s | 22664 MiB | 63.312; 1,93x | temperature 0,7, top_k 20, top_p 0,8, repetition_penalty 1,05 | no aplica (`reasoning` vacío) | solo inocuos (HF_TOKEN, Pinned memory) |
| qwen3-14b (Qwen3-14B-AWQ) | PASA | 248,2 s | 21336 MiB | 67.392; 2,06x | temperature 0,6, top_k 20, top_p 0,95 | `reasoning`; `enable_thinking:false` lo quita (sí) | ninguno |
| qwen3.5-27b (Qwen3.5-27B-GPTQ-Int4) | FALLA | no llegó (2 intentos) | 24084 MiB (monitor, en perfilado) | no comprobado | no comprobado | no comprobado | el servidor queda en «Capturing CUDA graphs 0/51»; hizo falta SIGKILL |
| qwen3.8-27b-amd (Quark AWQ W4A16) | FALLA | no llegó (2 intentos) | 18410 MiB (monitor, antes de la captura) | no comprobado | no comprobado | no comprobado | dos cuelgues de Windows (BSOD, hipervisor) en «Capturing CUDA graphs 0/51» |
| qwen3-30b-a3b (Qwen3-30B-A3B-GPTQ-Int4, MoE) | PASA | 399,0 s | 22422 MiB | 52.752; 1,61x | temperature 0,6, top_k 20, top_p 0,95 | `reasoning`; `enable_thinking:false` lo quita (sí) | ninguno |

## Notas
- **Avisos inocuos** (HF_TOKEN y «Pinned memory is not available…»): anotados en cada informe y no rebajan el veredicto, por indicación de Carlos. La línea de muestreo cuenta como dato.
- **Los dos 27B híbridos (Gated DeltaNet)** se quedan en la captura de CUDA graphs (0/51). `qwen3.5-27b`: 20 min en el intento 1 y corte a los 3 min en el 2; `py-spy` muestra trabajo en el autotuner de Triton y en `qwen_gdn_linear_attn.py` (volcado en `logs/pyspy_qwen3.5-27b.txt`). `qwen3.8-27b-amd`: el sistema se cuelga. **No he determinado la causa**: hipótesis sin comprobar son falta de VRAM (los pesos de qwen3.5 se reportan con 26,72 GiB sobre ~23,9 GiB) con desbordamiento a RAM por el driver de Windows, o un problema del kernel GDN en esta GPU. En qwen3.8 el perfilado fue corto (5,1 s) y la memoria quedó en 18410 MiB, lo que no apoya la primera.
- **Incidentes del entorno:** dos cuelgues de Windows con `qwen3.8-27b-amd` (13:3x y 13:57). Visor de eventos de Windows no revisado.
- **Herramienta añadida:** `py-spy 0.4.2`, instalado por Carlos en `~/llm-bench/tools`, solo con `dump --nonblocking`.
- **`nivel0.py`:** el límite hasta /health pasó de 20 a 25 min tras el primer intento de qwen3.5-27b (que usó 20). Se añadió un corte por log congelado 180 s en la captura de CUDA graphs.
- **Pendiente de revisar:** comprobar `Memoria de GPU compartida` en Windows durante un 27B; no se ha hecho.
