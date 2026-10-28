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
Task: call `get_track_metrics` **once** with `since` = <<detection_since>> and `until` = <<sim_time>> (from the start of the detection until now) and decide with that result. If the situation has returned to normal (the deviation goes down again and GPS and radar agree), close with `close_alert` and say why. If you think the problem continues (for example, another source is still wrong), do not close it: respond with `acknowledge_detection` (with the `alert_id`) and explain why in `reason`.

## reminder
You have not yet responded to: <<pending>>. A text does not count as a response: respond now by calling `publish_alert`, `acknowledge_detection` or `close_alert`.
