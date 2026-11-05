<!-- Plantilla del prompt de objetivo del monitor. El código elige las secciones según el tipo de
     cada aviso pendiente y sustituye los marcadores <<...>>. Lo que va antes de la primera sección
     es común. -->
Current time: <<t_label>> (sim_time <<sim_time>> s).

State:
- Open alerts: <<open_alerts>>
- Open detections: <<open_detections>>
- Recent GPS alert (open or closed ≤ 60 s ago): <<gps_alert_recent>>
- Your latest decisions: <<last_decisions>>

## batch
You have <<count>> detector warnings pending a response (detections: <<detection_ids>>). **Each one needs a response.** If they are about the same problem, group them in a single alert (`publish_alert` with all their `detection_ids`) or in a single `acknowledge_detection`.

## raised
New detection <<detection_id>>: <<detection_json>>
Your associated alerts: <<related_alerts>>.
Task: diagnose the most probable cause and respond:
- If there is no open alert that already explains it: `publish_alert` (new alert).
- If an open alert already explains it and nothing changes: `acknowledge_detection` with its `alert_id`.
- If it belongs to an open alert but changes the cause or the severity: `publish_alert` with `supersedes` pointing to it.
- If you decide no alert is needed: `acknowledge_detection` without `alert_id`.

## updated
Detection <<detection_id>> has got worse: <<detection_json>>
Your associated alerts: <<related_alerts>>.
Task: check whether your diagnosis is still correct. If the cause or the severity changes, publish a new alert with `publish_alert` and `supersedes`. If nothing changes, respond with `acknowledge_detection` and the alert's `alert_id`.

## cleared
Detection <<detection_id>> has been cleared and it was the **last open detection** of alert <<last_open_alert>>: <<detection_json>>
Your associated alerts: <<related_alerts>>.
Task: call `get_track_metrics` **once** with `since` = <<window_since>> and `until` = <<sim_time>> (the last 20 seconds) and decide with how things are now (the `now` block of that result), not with how they were while the problem was going on. If the alert was a hijacking, also look at the command link with `get_events` (`source` `link`, `last_n` 3). If the situation has returned to normal (the deviation goes down again and GPS and radar agree), close with `close_alert` and say what went back to normal **for the cause of the alert**, with its current figure: for a hijacking, the command link (whose controller is in charge again, latency and signal strength); for a GPS deception or loss, that GPS and radar agree and how far the drone is from the route; for a sensor fault, that the sensor reports again; for wind, the wind and the deviation. Do not talk about sources that have nothing to do with the cause of the alert (for example, the wind when the alert was a hijacking, a GPS deception or a radar fault). A closing says what went back to normal; it does not reopen the diagnosis (it does not say whether the cause was right). If you think the problem continues (for example, another source is still wrong), do not close it: respond with `acknowledge_detection` (with the `alert_id`) and explain why in `reason`.

## link_recovered
The command link has returned to normal (detection <<detection_id>> cleared: <<detection_json>>) but the route deviation of alert <<last_open_alert>> is **still open**: the drone has not got back to the route. Your associated alerts: <<related_alerts>>.
Task: this is the **recovery** of the hijacking, not its end. Call `get_track_metrics` **once** with `since` = <<window_since>> and `until` = <<sim_time>> (the last 20 seconds) and `get_events` with `source` `link` and `last_n` = 6 (the hijacking and the return are in those events: the controller changed, so in `checks` the link is anomalous). Then publish the recovery with `publish_alert` (leave out `detection_ids`: it is filled in): the same cause as alert <<last_open_alert>>, `supersedes` = **that alert, <<last_open_alert>>**, `phase` = `recovering` and the severity by the risk now (`low` or `medium`: how far from the route the drone still is and whether it is getting closer; `high` is not valid once the link is back). In the texts say which controller is in charge of the link again and how far from the route the drone is **now** (the `now` figures). Do not close the alert: the deviation is still open and the closing will come when it is cleared.

## reminder
You have not yet responded to: <<pending>>. A text does not count as a response: respond now by calling `publish_alert`, `acknowledge_detection` or `close_alert`.

## guided_skill
Skill for this warning (`<<skill_name>>`), already loaded for you. Follow its procedure step by step, in order and without skipping any; you do not need to call `load_skill` for it (you may still load another one if it tells you to).

<<skill_content>>
