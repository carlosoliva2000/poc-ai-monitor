"""Monitor de situación (E7c).

Características en tiempo real → tablas por faceta → seguidor de incidentes → política →
`IncidentUpdated` (contrato v1.1). No escribe ningún texto: eso es del asistente
(`ai_module.assistant`). Solo importa `bus_client`, `decision.table`, `ids`, `outbox` y
`poc_contracts`.
"""
