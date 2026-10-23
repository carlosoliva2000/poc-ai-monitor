---
name: report-format
description: Structure and style of the exercise's final report. Always use it before writing the report.
---
# Final report format

The report is a **Markdown** document, in English, for a person in charge who has not seen the simulation. Brief: it fits in a screen and a half. Times as T+mm:ss.

## Who writes what
The module assembles the final report with these parts, in this order:

1. **Header** (module): mission, scenario, duration, whether it was completed, waypoints and number of anomalies.
2. **Summary** (you).
3. **Timeline** (module): table with the detections, the alerts and the closures, with their time.
4. **Anomalies** (module and you): one subsection per anomaly (each chain of alerts that replace one another is **one** anomaly), with the time and severity of its first alert, the changes of the last one, the evidence and the status, written by the module. You write only the "What was seen" of each one.
5. **Monitor assessment** (you).
6. **Recommendations** (you).
7. **Limitations** (module).

## What you write
Respond with **only** these four sections, with these exact headings and in this order:

```markdown
## Summary
3–5 sentences: what happened, how many anomalies there were, which was the most serious and whether the monitor identified them in time.

## What was seen
### A1
2–3 sentences with figures and sources (what the detector saw and what the monitor checked). Without repeating the time, the severity or the status.
### A2
…

## Monitor assessment
Critically, in four bullets: **Support** (which checks support each cause and what doubt remains), **Delays**, **Fallbacks and rejections** (exact figures) and **Aids** (which ones it had active and how they may influence the result).

## Recommendations
1. …
2. …
```

## Rules
- Every figure comes from the data you are given. If you do not have a piece of data, write "not available".
- Do not write times, severities, statuses or ids that are not in the data; the module provides the facts.
- Do not copy the JSON of the data: turn it into sentences.
- No embellishments or conclusions that do not come from the data.
