"""El OpenAPI versionado en `contracts/api/` coincide con lo que generan las rutas."""

from platform_app.sim_api.export_openapi import DEFAULT_OUT, build_openapi, render


def test_openapi_file_is_up_to_date() -> None:
    assert DEFAULT_OUT.read_text(encoding="utf-8") == render(build_openapi()), (
        "sim-api-v1.json desactualizado: ejecuta platform_app.sim_api.export_openapi"
    )
