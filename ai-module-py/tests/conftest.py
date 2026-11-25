"""Tests pendientes de la E7c.

El módulo de IA actual (detector, tabla de la E6, monitor LLM, chats, informe) está **congelado**
mientras se rehace el simulador (E7a) y se sustituye por el monitor de situación (E7c) y el
asistente (E7d). El contrato de eventos v1.0 (E7a) quita campos que el módulo y sus tests usan
(`gust_mps`, `quality`, `radar_id`, `station_id`, `voltage_v`, `heading_deg` del GPS) y cambia la
física de `runs/` (simulador v2: el viento ya no desvía al dron, el secuestro corta la telemetría
y sin fix el GPS no da posición). Los ficheros de esta lista fallan, no se pueden importar o se
cuelgan esperando al bus. No se borran ni se editan: se vuelven a activar, adaptados, en la E7c.
"""

from pathlib import Path

import pytest

RUNS_V2 = "los `runs/` regenerados con el simulador v2 (otra física)"
PENDING_E7C = {
    "test_bus_client.py": "espera al bus de la plataforma con eventos v0.19 (se cuelga)",
    "test_coherence.py": "payloads v0.19",
    "test_detector_scenarios.py": RUNS_V2,
    "test_monitor_scenarios.py": RUNS_V2,
    "test_recovery.py": RUNS_V2,
    "test_detector_unit.py": "payloads v0.19 (`heading_deg`, `gust_mps`)",
    "test_e2e.py": "extremo a extremo con eventos v0.19",
    "test_e6_variants_offline.py": "variantes E6 con YAML v0.19",
    "test_enrich.py": "importa `MAX_WIND_GUST_MPS` (quitado en v1.0)",
    "test_guardrails.py": "payloads v0.19 (viento con racha)",
    "test_instructor.py": "importa `MAX_WIND_GUST_MPS` (quitado en v1.0)",
    "test_link_fill.py": "payloads v0.19",
    "test_link_back_time.py": "`LinkStatus` sin `controller_id` (v1.0, paso 7b)",
    "test_link_recovery.py": "payloads v0.19",
    "test_main.py": "importa el módulo con la racha del instructor",
    "test_model_check.py": "importa el módulo con la racha del instructor",
    "test_module_jump.py": "payloads v0.19",
    "test_monitor.py": "payloads v0.19",
    "test_monitor_memory.py": "payloads v0.19",
    "test_recovery_phase.py": "payloads v0.19",
    "test_round8.py": "payloads v0.19",
    "test_round9.py": "payloads v0.19 (`gust_mps`)",
    "test_run_matrix.py": "variantes E6 con YAML v0.19",
    "test_sensor_fault_source.py": "payloads v0.19",
    "test_state_recovery.py": "payloads v0.19",
    "test_table_engine.py": "hechos del viento con racha",
    "test_tool_call_events.py": "importa el módulo con la racha del instructor",
    "test_window_rules.py": "payloads v0.19",
}

# Tests concretos (no el fichero entero) que no se ejecutan hasta la E7c. Se saltan con su motivo,
# así el resto del fichero sigue corriendo.
DEMO_MOVED = (
    "el ajuste de `demo` del 7a movió los actos (viento T+125-160, engaño T+198-252, secuestro "
    "T+368-413) y el test construye la ejecución con los instantes de antes"
)
PENDING_E7C_TESTS: dict[str, dict[str, str]] = {
    "test_evaluate.py": dict.fromkeys(
        (
            "test_perfect_demo_is_all_green",
            "test_recovery_attributed_to_the_spoofing_counts_and_to_another_cause_does_not",
            "test_hijack_deviation_treated_as_recovery_is_flagged",
            "test_fallback_is_no_diagnosis",
            "test_acknowledge_takes_the_cause_of_the_alert_it_links_to",
            "test_write_evaluation_creates_both_files",
            "test_the_severity_of_each_published_alert_is_listed_by_label",
            "test_a_recovery_without_the_recovering_phase_is_a_miss_with_its_reason",
            "test_a_fallback_recovery_is_a_miss_and_the_veto_counts_come_from_the_trace",
            "test_the_module_jump_decides_the_reason_and_is_counted_apart",
        ),
        DEMO_MOVED,
    ),
}


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    for item in items:
        pending = PENDING_E7C_TESTS.get(Path(str(item.fspath)).name, {})
        name = getattr(item, "originalname", None) or item.name
        if name in pending:
            item.add_marker(pytest.mark.skip(reason=f"pendiente de la E7c: {pending[name]}"))


def pytest_ignore_collect(collection_path: Path) -> bool | None:
    if collection_path.name in PENDING_E7C:
        return True
    return None


def pytest_report_header() -> str:
    return f"E7c pendientes (no se ejecutan, contrato v1.0): {len(PENDING_E7C)} ficheros de tests"
