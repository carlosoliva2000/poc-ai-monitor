"""Monitor de situación (E7c, versión rápida para el vídeo del 19/11/2026).

Características en tiempo real → tablas por faceta → seguidor de incidentes → política →
`IncidentUpdated` (contrato v1.1). Con `assistant: scripted`, textos preparados del asistente
(`scripted.py`). Solo importa `bus_client`, `decision.table`, `ids`, `outbox` y `poc_contracts`:
no depende del módulo anterior, que sigue congelado.
"""
