---
name: report-format
description: Structure and style of the exercise's final report. Always use it before writing the report.
---
# Final report format

The report is a **Markdown** document, in English, for the person in charge of the drone, who has not seen the simulation. Brief: it fits in a screen and a half. Times as T+mm:ss.

## Who writes what
The module assembles the final report with these parts, in this order:

1. **Header** (module): mission, scenario, duration, whether it was completed, waypoints and number of anomalies.
2. **Summary** (you).
3. **Timeline** (module): table with the detections, the alerts and the closures, with their time.
4. **Anomalies** (module and you): one subsection per anomaly (each chain of alerts that replace one another is **one** anomaly), with the time and severity of its first alert, the changes of the last one, the evidence and the status, written by the module. You write only the "What was seen" of each one.
5. **Recommendations** (you).
6. **Limitations** (module).
7. **Annex: monitor self-assessment** (module and a second, separate writing for whoever evaluates the exercise): it is not part of what you write here.

## What you write
Respond with **only** these three sections, with these exact headings and in this order:

```markdown
## Summary
3–5 sentences: each anomaly with its type, when it happened and how it ended (closed, in recovery or still open), and which was the most serious and why.

## What was seen
### A1
2–3 sentences with figures and sources (what the detector saw and what the monitor checked). Without repeating the time, the severity or the status.
### A2
…

## Recommendations
1. What to do or check about the drone, the route, the link, the radar or the GPS, and why.
2. …
```

## Rules
- Every figure comes from the data you are given. If you do not have a piece of data, write "not available".
- Do not write times, severities, statuses or ids that are not in the data; the module provides the facts.
- Do not copy the JSON of the data: turn it into sentences.
- Say what is uncertain only if the data supports it. No embellishments or conclusions that do not come from the data.
