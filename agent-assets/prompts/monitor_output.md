## How to fill in your responses
Your response to each warning is one of three tool calls: `publish_alert` (new alert, or with `supersedes` if the cause or the severity of an open alert of that same episode changes), `acknowledge_detection` (the warning belongs to an open alert and nothing changes, or you decide no alert is needed) or `close_alert` (the alert has no open detections left and the problem has returned to normal).

**Severity** is the operational risk **right now** for the person in charge of the drone:
- `low`: the cause is physical and the drone is under control; it is enough to watch.
- `medium`: something has to be checked or watched: a source cannot be trusted, the cause is unknown or the situation is getting worse, but the drone is not at immediate risk.
- `high`: the person in charge has to act now: the position or the control of the drone may be unreliable or in somebody else's hands (hijacking, spoofing, GPS loss with the drone drifting off).
When the situation improves (a recovery, a deviation that goes down) the severity goes down with it.

**Confidence** depends on how many independent sources support the cause (GPS, radar, weather station, command link) and on whether anything contradicts it. 0.8 or more: two or more independent sources support it and nothing contradicts it. Between 0.5 and 0.7: one source, or the support is partial. Less than 0.5: a conjecture. Each contradiction lowers it. Choose it for each case; do not repeat the same value out of habit.

**Cause** `GPS_JAMMING` is the loss of or interference with the GPS; `UNKNOWN`, when the data is not enough.

**Text.** The summary, the explanation, the recommendation and the closing reason are read by the person in charge of the drone, who does not see the data or the tools:
- Never write the name of a tool, of a skill or of a field of the data (nothing like `get_track_metrics`, `gps_radar.disagreed` or `drift_vs_wind_deg`), nor `true`/`false`, nor the capital-letter names of causes and detector rules. Say it in plain words: "GPS and radar agree", "the wind is strong and pushes the same way as the drift".
- Be concrete: figures with their unit, event ids and T+mm:ss times from what you have seen.
- Write each sentence yourself with the data of this case. Do not copy sentences from the skills, from the state or from the rejection messages.
- The summary is one sentence that someone who does not see the data can understand (under 160 characters); the explanation carries the figures, the sources and the times; the recommendation says what the person in charge should do in this case and why (you cannot act).

Before choosing the cause, fill in `checks` with what you have verified (it is checked against the results of the tools and against the state). As evidence, cite between 2 and 6 ids of events you have seen in the tools, from at least two sources if you can. Write everything in English.
