# Comparativa nivel 1 · API y herramientas

Generada el 23/10/2026 a partir de `nivel1_<clave>.json`. Celdas: aprobadas/repeticiones; **—** = no comprobado (el candidato no tiene ese modo).

| candidato | veredicto | 1 A | 2 A | 3 A | 4 A | 5 A | 6a A | 6b A | 7 A | 8a A | 8b A | 9 A | 1 B-800 | 2 B-800 | 3 B-800 | 4 B-800 | 5 B-800 | 6a B-800 | 6b B-800 | 7 B-800 | 8a B-800 | 8b B-800 | 9 B-800 | 1 B-4000 | 2 B-4000 | 3 B-4000 | 4 B-4000 | 5 B-4000 | 6a B-4000 | 6b B-4000 | 7 B-4000 | 8a B-4000 | 8b B-4000 | 9 B-4000 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| actual | FALLA | 5/5 | 5/5 | 5/5 | 5/5 | 5/5 | 5/5 | 0/5 | 0/5 | 5/5 | 5/5 | 5/5 | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| qwen3-14b | PASA | 5/5 | 5/5 | 5/5 | 5/5 | 5/5 | 5/5 | 5/5 | 5/5 | 5/5 | 5/5 | 5/5 | 5/5 | 5/5 | 5/5 | 5/5 | 5/5 | 5/5 | 5/5 | 5/5 | 5/5 | 5/5 | 5/5 | 5/5 | 5/5 | 5/5 | 5/5 | 5/5 | 5/5 | 5/5 | 5/5 | 5/5 | 5/5 | 5/5 |
| qwen3-30b-a3b | PASA | 5/5 | 5/5 | 5/5 | 5/5 | 5/5 | 5/5 | 5/5 | 5/5 | 5/5 | 0/5 | 5/5 | 5/5 | 5/5 | 5/5 | 5/5 | 5/5 | 5/5 | 5/5 | 5/5 | 5/5 | 0/5 | 5/5 | 5/5 | 5/5 | 5/5 | 5/5 | 5/5 | 5/5 | 5/5 | 5/5 | 5/5 | 0/5 | 5/5 |

Casos: 1 = auto; 2 = auto con strict; 3 = required; 4 = función por nombre; 5 = negativo (sin herramienta); 6a = bucle: 1 herramienta; 6b = bucle: 2 herramientas encadenadas; 7 = tipos de argumentos; 8a = idioma: EN→EN; 8b = idioma: usuario ES, sistema «always English» (informativo); 9 = limpieza de content / reasoning. 8b es informativo.

## Tabla compacta (una columna por caso; cada celda A / B-800 / B-4000)

| candidato | 1 | 2 | 3 | 4 | 5 | 6a | 6b | 7 | 8a | 8b | 9 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| actual | 5/5 / — / — | 5/5 / — / — | 5/5 / — / — | 5/5 / — / — | 5/5 / — / — | 5/5 / — / — | 0/5 / — / — | 0/5 / — / — | 5/5 / — / — | 5/5 / — / — | 5/5 / — / — |
| qwen3-14b | 5/5 / 5/5 / 5/5 | 5/5 / 5/5 / 5/5 | 5/5 / 5/5 / 5/5 | 5/5 / 5/5 / 5/5 | 5/5 / 5/5 / 5/5 | 5/5 / 5/5 / 5/5 | 5/5 / 5/5 / 5/5 | 5/5 / 5/5 / 5/5 | 5/5 / 5/5 / 5/5 | 5/5 / 5/5 / 5/5 | 5/5 / 5/5 / 5/5 |
| qwen3-30b-a3b | 5/5 / 5/5 / 5/5 | 5/5 / 5/5 / 5/5 | 5/5 / 5/5 / 5/5 | 5/5 / 5/5 / 5/5 | 5/5 / 5/5 / 5/5 | 5/5 / 5/5 / 5/5 | 5/5 / 5/5 / 5/5 | 5/5 / 5/5 / 5/5 | 5/5 / 5/5 / 5/5 | 0/5 / 0/5 / 0/5 | 5/5 / 5/5 / 5/5 |

## Veredictos y motivos

- **actual: FALLA** — modo A por debajo de 5/5 en: 6b (0/5), 7 (0/5)
- **qwen3-14b: PASA** — modo A 5/5 en los casos 1 a 9 (incluidas las variantes 6a/6b y 8a).
- **qwen3-30b-a3b: PASA** — modo A 5/5 en los casos 1 a 9 (incluidas las variantes 6a/6b y 8a).

## Fallos del modo B (no rebajan el veredicto)

- qwen3-14b B-800: sin fallos · respuestas con finish_reason=length: 0/75
- qwen3-14b B-4000: sin fallos · respuestas con finish_reason=length: 0/75
- qwen3-30b-a3b B-800: sin fallos · respuestas con finish_reason=length: 0/75
- qwen3-30b-a3b B-4000: sin fallos · respuestas con finish_reason=length: 0/75

## Velocidad (mediana de las repeticiones válidas)

| candidato | modo | generación tok/s | TTFT 1.er token s | memoria GPU máx MiB |
|---|---|---|---|---|
| actual | A | 64.1 | 0.034 | 22664.0 |
| qwen3-14b | A | 65.65 | 0.032 | 22598.0 |
| qwen3-14b | B-800 | 64.8 | 0.048 | 22600.0 |
| qwen3-14b | B-4000 | 64.85 | 0.049 | 22600.0 |
| qwen3-30b-a3b | A | 158.6 | 0.017 | 22784.0 |
| qwen3-30b-a3b | B-800 | 150.85 | 0.033 | 22786.0 |
| qwen3-30b-a3b | B-4000 | 151.95 | 0.029 | 22786.0 |

## No comprobado

- Candidatos no ejecutados en este nivel (aparcados por decisión de Carlos): qwen3.5-27b, qwen3.8-27b-amd.
- Ver la sección «No comprobado» de cada `nivel1_<clave>.md`.
