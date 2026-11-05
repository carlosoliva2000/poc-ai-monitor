---
name: source-discrepancy
description: Use it when the detector raises SOURCE_DISCREPANCY (GPS and radar do not agree), SOURCE_SILENT (a source stops reporting) or GPS_DEGRADED (the GPS reports with no fix, few satellites or high hdop), or when, while diagnosing something else, you see that GPS and radar do not agree. It tells apart GPS spoofing, GPS loss or interference (jamming), sensor fault and a source that stops reporting.
---
# GPS–radar discrepancy, degraded GPS or silent source

`SOURCE_SILENT` → step 5. `GPS_DEGRADED` → step 4. `SOURCE_DISCREPANCY` → start at step 0. The facts come computed in `get_track_metrics`: read the `true`/`false` fields, do not compare numbers yourself.

Context: the radar has no bias (it says where the drone really is); the drone navigates with its GPS, so if the GPS lies the drone **really drifts off** while the GPS looks perfect. A spoofing does not degrade the fix (`3d`, ~14 satellites, `hdop` ~1); a GPS loss does (`fix: none`, `sats` 0, `hdop` 99.9).

Window or now: decide and fill in `checks` with the facts of the window of `get_track_metrics`; to say how things are at this moment (do GPS and radar agree now, how far off the route each one is now), use its `now` block, not the mean or the maximum of the window (which tell what happened, in the past tense). Never write that GPS and radar disagree by the distance of `now`. If `now` says the GPS has no fix, its position is only an estimate: there is no GPS–radar comparison or GPS deviation for the present, and the radar is the reference.

## 0. Is there already an open GPS alert that explains it?
If a `GPS_JAMMING` or `SENSOR_FAULT` alert of the GPS is open and the `GPS_DEGRADED` detection is still open, this discrepancy is a consequence of the GPS loss, not a new problem.
- `SENSOR_FAULT` alert: publish `GPS_JAMMING` with `supersedes` pointing to it; the loss is now confirmed.
- `GPS_JAMMING` alert with `severity: medium` and `gps_radar.disagreed` is now `true` (the drone already drifts): publish `GPS_JAMMING` with `supersedes` pointing to it and the severity that the drift now deserves.
- `GPS_JAMMING` alert that already has the severity the situation deserves, or `medium` while `gps_radar.disagreed` is still `false`: `acknowledge_detection` with its `alert_id`.
Otherwise, continue.

## 1. Metrics
Call `get_track_metrics` with `since` = sim_time of the detection − 40 and `until` = now; do not shorten the window, because the radar reports every 2 seconds and a window of a second or two may hold no sample of it. `radar_available: false` only says that this window has no radar sample: the radar is silent only if its deviation in `now` is missing as well and its last events (`get_events`, `source` `radar`) are old. If the radar really is silent, you cannot check the GPS: say so.

## 2. Spoofing or GPS loss?
Conditions for the deception: `gps_radar.disagreed` is `true`, the GPS is on the plan (`gps_deviation_from_plan_m.mean` < 15) and the radar is outside and moving away.
**Before concluding spoofing**, call `get_events` with `source` = `gps` and `last_n` = 5: if there is `fix: none`, `sats: 0` or `hdop` 99.9 it is a GPS loss (step 4); if the fix is normal, it is spoofing: **`GPS_SPOOFING`**.

## 3. Sensor fault?
A discrepancy that appears suddenly and disappears without a pattern, radar with `quality` < 0.5, or degraded GPS without discrepancy: **`SENSOR_FAULT`**; say which sensor fails. If nothing fits: `UNKNOWN` with `confidence` ≤ 0.4.
If the discrepancy disappears suddenly because the GPS jumps to the radar, the deception has ended: the deviation that follows is real (step 2 of `route-deviation`).

## 4. Degraded GPS (`GPS_DEGRADED`)
Call `get_events` with `source` = `gps` and `last_n` = 5 (`fix`, `sats`, `hdop`) and `get_track_metrics` with `since` = sim_time of the detection − 20.
- Bad fix (`fix: none`, `sats` 0 or `hdop` 20 or more): **`GPS_JAMMING`** (loss or interference of the GPS). The risk is higher if `gps_radar.disagreed` is `true` (the drone navigates by dead reckoning and drifts off) than if it is not yet.
- Only a somewhat high `hdop` or few satellites, with a fix and `gps_radar.disagreed` `false`: **`SENSOR_FAULT`**.
- If the radar goes silent at the same time, the deviation cannot be confirmed: `confidence` 0.7 at most (the `fix: none` is enough).
- When `GPS_DEGRADED` is cleared, the position jumps to the real one and it is normal for `ROUTE_DEVIATION` to be raised (step 2 of `route-deviation`).

## 5. Silent source (`SOURCE_SILENT`)
The detection carries `source` and `value` (seconds). **It is always a different fault and carries its own alert**, even if another one is open. Look with `get_events` (`last_n` = 2) at which sources continue: gps, radar and link.
- Only the radar goes silent: radar fault; the GPS can no longer be checked (say so).
- Only the GPS goes silent and the link continues: receiver fault; the position is only known through the radar.
- GPS and link go silent: loss of communications with the drone.
- Weather or battery goes silent: minor fault (without weather the wind cannot be confirmed).
The cause is **`SENSOR_FAULT`** (`UNKNOWN` if several go silent for no clear reason). The risk is higher if the GPS or the radar goes silent while another detection is open (the position can no longer be checked). The summary says which source is silent. When it is cleared, `close_alert` with how long it was silent.

## When publishing
Fill in `checks` with what you have seen (it is checked against the tools): `gps_alert_recent` (the "Recent GPS alert" line of the state: yes = `true`), `gps_radar_disagreed`, `wind_notable`, `wind_with_drift`, `link_checked` and `link_anomalous` (`null` if you did not look at the link). Evidence: ids from `first_event_ids`/`last_event_ids` and some `PositionUpdated`.
