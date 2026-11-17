<!-- E6: mensaje de usuario del enriquecimiento. `<<alert>>` y `<<facts>>` los escribe el módulo
en frases (sin nombres de campos); `<<hypothesis_section>>` es una de las dos secciones de abajo:
`hypothesis` solo cuando la causa de la alerta es UNKNOWN. -->
The alert, as decided by the module's rules:
<<alert>>

What the module saw when it decided:
<<facts>>

<<hypothesis_section>>

## hypothesis
The cause is unknown: the facts did not fit any known cause. Only if the facts above clearly suggest one, you may add a hypothesis. It is not a diagnosis and the text must not present it as one:
"hypothesis": {"cause": one of "WIND", "HIJACK", "GPS_SPOOFING", "GPS_JAMMING" or "SENSOR_FAULT", "confidence": a number not above 0.4, "evidence_event_ids": [one or more ids from this list]}
Event ids you may cite: <<seen_ids>>
Otherwise, leave "hypothesis": null.

## no_hypothesis
Leave "hypothesis": null.
