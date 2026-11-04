---
name: route-deviation
description: Use it when the detector raises ROUTE_DEVIATION (the GPS position drifts away from the planned route). It tells apart wind, hijacking, recovery after a spoofing or a GPS loss, and unknown cause.
---
# Route deviation

The drone's GPS is far from the route. Follow the steps **in order** and stop at the first one that fits. The facts come computed in `get_track_metrics`: **do not compare numbers or angles yourself**, read the `true`/`false` fields.

## 1. Metrics
Call `get_track_metrics` with `since` = sim_time of the detection − 30 and `until` = now.

## 2. GPS recovery after a spoofing or a loss? (it takes precedence over everything else)
It is a recovery if **both**: the "Recent GPS alert" line of the state says **yes** **and** `gps_radar.disagreed` is `true` or `gps_max_step_m` ≥ 30 (the GPS has just jumped to the real position).
- **The only valid cause is that of that alert** (the state line tells it: "If this warning is the GPS recovery: cause X, supersedes ai-XXXX"). `severity: medium`. Say that the GPS is back and the drone is correcting towards the route. `supersedes` = that alert if it is still open. It is not wind or hijacking even if the deviation is large. Recommendation: verify the GPS receiver.

## 3. Do GPS and radar disagree?
If `gps_radar.disagreed` is `true` (and it is not step 2), load the skill `source-discrepancy`.

## 4. Wind?
- It is **`WIND`** only if `wind.notable` **and** `wind.with_drift` are `true`. `severity: low` if `gps_deviation_from_plan_m.max` < 80 and it does not grow; otherwise `medium`. `confidence` 0.8–0.9. Evidence: `wind.last_event_id` and `first_event_ids`/`last_event_ids`. Recommendation: no intervention; watch that it recovers the route.
- If either is `false` (or `wind` is `null`), **it is not wind: go to step 5.**

## 5. Hijacking? Look at the link
Call `get_events` with `source` = `link` and `last_n` = 6. The link is anomalous if the `controller_id` changes (e.g. `UNK-4F2A` instead of `GCS-1`), `rssi_dbm` varies by more than 10 dB or `latency_ms` is multiplied.
- Anomalous link → **`HIJACK`**, `severity: high`, `confidence` 0.8–0.9. Evidence: the `LinkStatus` events that changed.
- Normal link but `course_deg` differs by more than 45° from `bearing_to_next_waypoint_deg` and the deviation grows → `HIJACK` with `confidence` 0.6–0.7 (only if the "Recent GPS alert" line of the state says **no**).
- Recommendation: notify the person in charge of the drone and verify the command link.

## 6. Nothing fits
`UNKNOWN`, `severity: medium`, `confidence` ≤ 0.4; say what you have checked.

## When publishing
Fill in `checks` with what you have seen (do not invent: it is checked against the tools): `gps_alert_recent` (the "Recent GPS alert" line of the state: yes = `true`), `gps_radar_disagreed`, `wind_notable` and `wind_with_drift` (from `get_track_metrics`), `link_checked` and `link_anomalous` (`null` if you did not look at the link).
