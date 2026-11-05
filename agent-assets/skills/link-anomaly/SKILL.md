---
name: link-anomaly
description: Use it when the detector raises LINK_ANOMALY (the command link changes controller, or its signal or latency degrade). It tells apart a hijacking (another controller takes the link) from a degraded link.
---
# Command link anomaly

The detector watches the command link. It raises when the controller (`controller_id`) stops being the one of the mission (the first one seen) or when the latency or the signal strength leave their normal range, and it clears when the controller of the mission is back and the link is normal again. It does not know the cause: you decide it.

## 1. Look at the link
Call `get_events` with `source` = `link` and `last_n` = 6. Read the `controller_id` of each event (a controller that is not the one of the first events is somebody else on the link), the `rssi_dbm` and the `latency_ms`.

## 2. Another controller: hijacking
If the `controller_id` changed (for example `UNK-4F2A` instead of `GCS-1`) the command link is in other hands: the cause is **`HIJACK`**. Evidence: the `LinkStatus` events that changed. The drone may still be on the route: do not wait for it to leave it. Call `get_track_metrics` with `since` = sim_time of the detection − 30 and `until` = now, to say how far from the route the drone is and whether GPS and radar agree.

## 3. Same controller, degraded link
If the controller did not change and only the latency or the signal degrade, the link is weak but nobody has taken it: the cause is **`SENSOR_FAULT`** (the command link degrades; say it) with `confidence` 0.6 at most, or `UNKNOWN` if you cannot say more.

## 4. The link comes back
When the detection is cleared the warning tells you what to do. If the route deviation of the hijacking is still open, it is the **recovery** of the hijacking (the warning asks for it); if nothing else is open, close with `close_alert` and say which controller is in charge of the link again.

## When publishing
Fill in `checks` with what you have seen (it is checked against the tools): `gps_alert_recent` (the "Recent GPS alert" line of the state: yes = `true`), `gps_radar_disagreed`, `wind_notable` and `wind_with_drift` (from `get_track_metrics`; `false` if you did not call it), `link_checked` = `true` and `link_anomalous` (`true` if the controller changed or the link degrades in the events you saw).
