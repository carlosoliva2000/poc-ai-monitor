---
name: link-anomaly
description: Use it when the detector raises LINK_ANOMALY (the command link changes controller, or its signal or latency degrade). It tells apart a hijacking (another controller takes the link) from a degraded link.
---
# Command link anomaly

The detector watches the command link. It raises when the controller (`controller_id`) stops being the one of the mission (the first one seen) or when the latency or the signal strength leave their normal range, and it clears when the controller of the mission is back and the link is normal again. It does not know the cause: you decide it.

## 1. Look at the link
Call `get_events` with `source` = `link` and `last_n` = 6. Read the `controller_id` of each event (a controller that is not the one of the first events is somebody else on the link), the `rssi_dbm` and the `latency_ms`.

## 2. Another controller: hijacking
If the controller changed (for example `UNK-4F2A` instead of `GCS-1`) the command link is in other hands: the cause is **`HIJACK`**. Evidence: the `LinkStatus` events that changed. The drone may still be on the route: do not wait for it to leave it. Call `get_track_metrics` with `since` = sim_time of the detection − 30 and `until` = now, to know how far from the route the drone is and whether GPS and radar agree.

## 3. Same controller, degraded link
If the controller did not change and only the latency or the signal degrade, the link is weak but nobody has taken it: it is a fault of the link, not a hijacking. Say that the link degrades and which figures show it. The confidence cannot be high (0.6 at most): one source only. If you cannot say more, the cause is unknown.

## 4. The link comes back
The warning of the clearing tells you what to do:
- If the route deviation of the hijacking is still open, it is the **recovery** of the hijacking: the hijacking is over for the link but not for the flight. Say that the link is back with the controller of the mission and **when** (the time of the first link event with that controller, not the time of the warning, which comes later because the detector waits to be sure), and describe where the drone is: how far from the route and whether it is getting closer, moving away or holding steady **now** (the trend of the last seconds, in the block of the present; the trend of the window also counts the time before the link came back and can still say that the deviation grows). The severity is the risk now: while the drone is far from the route there is something to watch; once it is close and GPS and radar agree, watching is enough.
- If nothing else is open, the problem is over: close the alert and say which controller is in charge of the link again.

## Writing
The person in charge reads the text, not the data: say it in plain words (the link went to another controller and came back, the drone is getting closer to the route, GPS and radar agree), with figures, event ids and T+mm:ss times, and without names of fields, tools or `true`/`false`. Write each sentence with the data of this case.

## When publishing
Fill in `checks` with what you have seen (it is checked against the tools): `gps_alert_recent` (the "Recent GPS alert" line of the state: yes = `true`), `gps_radar_disagreed`, `wind_notable` and `wind_with_drift` (from `get_track_metrics`; `false` if you did not call it), `link_checked` = `true` and `link_anomalous` (`true` if the controller changed or the link degrades in the events you saw).
