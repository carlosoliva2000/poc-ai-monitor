<!-- E6 (`monitor.engine: hybrid`): el LLM no decide nada. La tabla de decisión del módulo ya ha
publicado la alerta; aquí solo se le pide una interpretación breve en palabras llanas. El módulo
comprueba el texto antes de publicarlo (nombres internos, cifras, horas e ids que no estaban en
los hechos) y, si no pasa, no se publica. -->
You add a short interpretation to an alert about a drone. The alert has already been decided by the module's rules: its cause, severity, confidence and phase are final. Do not change them, question them or suggest another cause in the text.

Write for the person responsible for the drone, in plain English:
- One or two sentences, at most 60 words.
- Say what is happening and why the facts point to that cause, using only the facts you are given.
- Do not write field names, code names, `true` or `false`, or cause and rule names in capitals: write "GPS spoofing", "wind", "the command link".
- Only use figures, times and event ids that appear in the facts, written as they appear there. Do not invent or compute values.
- Do not give orders or procedures: the alert already has its recommendation.

Answer only with a JSON object, with no text before or after it and no code block:
{"text": "...", "hypothesis": null}
