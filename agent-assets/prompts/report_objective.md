The simulation "<<scenario>>" (run <<run_id>>) finished at <<t_label>> (sim_time <<sim_time>> s). Write the three sections that are yours. Labels of the anomalies: <<labels>>.

## Flight summary
<<flight_summary>>

## Anomalies (each one is a chain of alerts)
<<anomalies>>

## What you have to write
Respond directly with these headings and in this order, without a code block or text before or after:
- `## Summary`: 3–5 sentences. What happened in the flight, how many anomalies there were, which was the most serious and whether any is open at the end.
- `## What was seen`: a subsection `### A1`, `### A2`… for each anomaly in the list (with its label), of 2–3 sentences with the figures and the sources of the data above. Do not repeat the time, the severity or the status.
- `## Recommendations`: 2–4 numbered, concrete points for the person in charge of the drone that come from the data above (what to check or do after this flight). Do not propose training the model or changes to the monitoring system.
