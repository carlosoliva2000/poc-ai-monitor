"""`contracts/schemas/` coincide con lo que generan los modelos (regla 2 del CLAUDE.md)."""

from pathlib import Path

from poc_contracts.export_schemas import DEFAULT_OUT, build_schemas, render


def test_schemas_directory_is_up_to_date() -> None:
    expected = {rel: render(schema) for rel, schema in build_schemas().items()}
    on_disk = {
        p.relative_to(DEFAULT_OUT).as_posix(): p.read_text(encoding="utf-8")
        for p in Path(DEFAULT_OUT).rglob("*.json")
    }
    assert set(on_disk) == set(expected), "ficheros de más o de menos: regenera los esquemas"
    stale = [rel for rel in expected if on_disk[rel] != expected[rel]]
    assert not stale, f"esquemas desactualizados (ejecuta export_schemas): {stale}"
