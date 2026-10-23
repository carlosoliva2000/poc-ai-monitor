The simulation "<<scenario>>" (run <<run_id>>) finished at <<t_label>> (sim_time <<sim_time>> s). Write the four sections that are yours. Labels of the anomalies: <<labels>>.

## Flight summary
<<flight_summary>>

## Anomalies (each one is a chain of alerts)
<<anomalies>>

## Data to assess the monitor
<<assessment_facts>>

## What you have to write
Respond directly with these headings and in this order, without a code block or text before or after:
- `## Summary`: 3–5 sentences. What happened in the flight, how many anomalies there were, which was the most serious and whether any is open at the end.
- `## What was seen`: a subsection `### A1`, `### A2`… for each anomaly in the list (with its label), of 2–3 sentences with the figures and the sources of the data above. Do not repeat the time, the severity or the status.
- `## Monitor assessment`: be critical. Four bullets, with these labels:
  - **Support:** one sentence per anomaly (A1, A2…): which checks and data support the cause and what doubt remains (checks that do not fit each other, cause or severity that changed according to "Changes from the first alert to the last", evidence not seen in the data). Write "supported by…"; do not write "correct", "accurate" or "got it right".
  - **Delays:** the figures from "Delays" (simulation and wall clock) and whether they seem long for an operator.
  - **Fallbacks and rejections:** the exact number of fallbacks and the number of calls rejected by the guardrails (they are different numbers; those from "Fallbacks" and "Guardrail rejections"), and what the monitor had to correct (one sentence per rejection reason). If there are rejections, do not write that there were none.
  - **Aids:** name each aid in the list "Active model aids" and say which part of the result may be due to them (without them the model could fail).
- `## Recommendations`: 2–4 numbered, concrete points, for the person in charge of the drone or of the exercise, that come from the data above (which alert or check to review, which delay to reduce). Do not propose training the model.
