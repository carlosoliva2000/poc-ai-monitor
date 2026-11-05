The simulation "<<scenario>>" (run <<run_id>>) finished at <<t_label>> (sim_time <<sim_time>> s). Write the three sections that are yours. Labels of the anomalies: <<labels>>.

## Flight summary
<<flight_summary>>

## Anomalies (each one is a chain of alerts)
<<anomalies>>

## What you have to write
Respond directly with these headings and in this order, without a code block or text before or after:
- `## Summary`: 3–5 sentences. Name **each** anomaly with its type (wind, GPS spoofing, GPS loss or interference, hijacking, sensor fault…), when it happened and how it ended (closed, in recovery or still open), and say which was the most serious and why.
- `## What was seen`: a subsection `### A1`, `### A2`… for each anomaly in the list (with its label), of 2–3 sentences with the figures and the sources of the data above. Do not repeat the time, the severity or the status.
- `## Recommendations`: 2–4 numbered, operational points for the person in charge of the drone, each with its reason, that come from the causes of the anomalies above (what to do or check about the drone, the route, the link, the radar or the GPS after this flight). Only what the data or the notes support: no figures, thresholds or deadlines of your own and nothing the data does not point to. Nothing about the monitoring system: that goes to the annex. Do not propose training the model.
