"""Pruebas del generador de variantes (E7b, paso 1):

uv run --project platform pytest tools/training/tests
"""

import math
from collections import Counter
from pathlib import Path

import variants
import yaml

from poc_contracts.scenario import ScenarioConfig

MANIFEST = yaml.safe_load(variants.DEFAULT_MANIFEST.read_text(encoding="utf-8"))


def _fault_windows(raw: dict) -> dict[str, list[tuple[float, float]]]:
    out: dict[str, list[tuple[float, float]]] = {}
    for f in raw["faults"]:
        out.setdefault(f["source"], []).append((f["start_s"], f["end_s"]))
    return out


def test_stable_int_does_not_depend_on_the_interpreter_hash() -> None:
    assert variants.stable_int(7011, 3, 0) == variants.stable_int(7011, 3, 0)
    assert variants.stable_int("a") == 3904355907  # crc32("a"), fijo en cualquier ejecución


def test_a_variant_is_deterministic() -> None:
    a = variants.sample_variant(MANIFEST, 5, "spoofing", 0)
    b = variants.sample_variant(MANIFEST, 5, "spoofing", 0)
    assert a == b
    assert variants.sample_variant(MANIFEST, 5, "spoofing", 1) != a  # otro intento, otra variante


def test_quotas_are_exact_and_stable() -> None:
    families = variants.quota_families(MANIFEST, 1600)
    counts = Counter(families)
    assert len(families) == 1600
    for family, share in MANIFEST["quotas"].items():
        assert counts[family] == round(share * 1600)
    assert families == variants.quota_families(MANIFEST, 1600)


def test_every_family_gives_a_valid_scenario_within_the_ranges() -> None:
    r = MANIFEST["ranges"]
    for i, family in enumerate(variants.FAMILIES):
        raw, meta = variants.sample_variant(MANIFEST, i, family, 0)
        cfg = ScenarioConfig.model_validate(raw)
        assert r["drone"]["cruise_speed_mps"][0] <= cfg.drone.cruise_speed_mps <= 15
        assert r["drone"]["max_turn_rate_dps"][0] <= cfg.drone.max_turn_rate_dps <= 120
        assert r["drone"]["lookahead_m"][0] <= cfg.drone.lookahead_m <= 40
        assert 240 <= meta["plan_duration_s"] <= 1100
        pts = [(0.0, 0.0)] + [(w.x, w.y) for w in cfg.mission.waypoints] + [(0.0, 0.0)]
        assert all(math.dist(a, b) >= 300 for a, b in zip(pts, pts[1:], strict=False))
        assert meta["anomalies"][0]["family"] == family or family == "nominal"


def test_same_source_faults_never_overlap() -> None:
    for i in range(60):
        family = list(variants.FAMILIES)[i % len(variants.FAMILIES)]
        raw, _ = variants.sample_variant(MANIFEST, 100 + i, family, 0)
        for windows in _fault_windows(raw).values():
            windows.sort()
            assert all(a[1] <= b[0] for a, b in zip(windows, windows[1:], strict=False))
        for source in ("gps", "link"):
            episodes = raw["sensors"][source]["episodes"]
            faults = _fault_windows(raw).get(source, [])
            for e in episodes:
                if source == "link":
                    assert not any(variants.overlaps((e["start_s"], e["end_s"]), f) for f in faults)


def test_the_split_is_by_variant_and_covers_everything() -> None:
    metas = [
        {"name": f"v{i:04d}", "family": fam}
        for i, fam in enumerate(variants.quota_families(MANIFEST, 400))
    ]
    split = variants.assign_splits(MANIFEST, metas)
    assert set(split) == {m["name"] for m in metas}  # cada variante en una sola partición
    assert Counter(split.values()) == {"train": 280, "validation": 60, "test": 60} or abs(
        Counter(split.values())["train"] - 280
    ) <= len(variants.FAMILIES)
    by_family: dict[str, Counter] = {}
    for m in metas:
        by_family.setdefault(m["family"], Counter())[split[m["name"]]] += 1
    assert all(c["validation"] >= 1 and c["test"] >= 1 for c in by_family.values())
    assert split == variants.assign_splits(MANIFEST, metas)


def test_the_dataset_is_reproducible_byte_for_byte(tmp_path: Path) -> None:
    a = variants.build(MANIFEST | {"dataset": "a"}, tmp_path, workers=1, n=5)
    b = variants.build(MANIFEST | {"dataset": "a"}, tmp_path / "second", workers=1, n=5)
    files_a = sorted(p.relative_to(a) for p in a.rglob("*") if p.is_file())
    assert files_a == sorted(p.relative_to(b) for p in b.rglob("*") if p.is_file())
    for rel in files_a:
        if rel.name != "timing.json":  # los tiempos son de la máquina
            assert (a / rel).read_bytes() == (b / rel).read_bytes(), rel


def test_a_variant_leaves_no_truth_and_no_scenario_name_in_its_events(tmp_path: Path) -> None:
    out = variants.build(MANIFEST | {"dataset": "x"}, tmp_path, workers=1, n=3)
    folder = next((out / "variants").iterdir())
    assert sorted(p.name for p in folder.iterdir()) == [
        "assets.yaml", "events.jsonl.gz", "meta.json", "scenario.yaml", "states.jsonl.gz",
    ]  # fmt: skip


# --- e7b-v2: el dron y los sensores de cada variante --------------------------------------------

V2 = yaml.safe_load((variants.DEFAULT_MANIFEST.parent / "e7b-v2.yaml").read_text(encoding="utf-8"))
GEN = yaml.safe_load(
    (variants.DEFAULT_MANIFEST.parent / "e7b-gen.yaml").read_text(encoding="utf-8")
)


def test_v2_drone_and_sensors_are_sampled_within_their_ranges() -> None:
    r = V2["ranges"]
    seen_air, seen_period = set(), set()
    for i, family in enumerate(list(variants.FAMILIES) * 3):
        raw, _ = variants.sample_variant(V2, i, family, 0)
        d, s = raw["drone"], raw["sensors"]
        assert 10 <= d["max_airspeed_mps"] <= 23
        assert 0.6 - 1e-2 <= d["wind_limit_mps"] / d["max_airspeed_mps"] <= 0.85 + 1e-2
        assert 0.5 - 1e-2 <= d["cruise_speed_mps"] / d["max_airspeed_mps"] <= 0.9 + 1e-2
        assert r["gps"]["gm_sigma_m"][0] <= s["gps"]["gm_sigma_m"] <= r["gps"]["gm_sigma_m"][1]
        assert r["radar"]["sigma0_m"][0] <= s["radar"]["sigma_m"] <= r["radar"]["sigma0_m"][1]
        for source, periods in r["periods_s"].items():
            assert s[source]["period_s"] in periods
        seen_air.add(d["max_airspeed_mps"])
        seen_period.add(s["gps"]["period_s"])
    assert len(seen_air) > 10 and len(seen_period) >= 2  # variantes distintas, no una constante


def test_v2_wind_episodes_are_relative_to_the_drone_of_each_variant() -> None:
    bands = {"notable": 0, "beyond_limit": 0, "drifting": 0}
    for i in range(60):
        raw, _ = variants.sample_variant(V2, i, "wind", 0)
        limit, air = raw["drone"]["wind_limit_mps"], raw["drone"]["max_airspeed_mps"]
        for ep in raw["wind"]["episodes"]:
            speed = ep["speed_mps"]
            assert 4.5 <= speed <= 1.4 * air + 0.1
            bands[
                "notable" if speed < limit else "beyond_limit" if speed < air else "drifting"
            ] += 1
    assert all(bands.values())  # salen las tres bandas, cada una respecto a su dron


def test_each_variant_writes_the_assets_the_monitor_would_know() -> None:
    raw, _ = variants.sample_variant(V2, 3, "spoofing", 0)
    a = variants.assets_of(raw)
    assert a["drone"] == {
        "max_airspeed_mps": raw["drone"]["max_airspeed_mps"],
        "wind_limit_mps": raw["drone"]["wind_limit_mps"],
        "cruise_mps": raw["drone"]["cruise_speed_mps"],
    }
    assert a["periods_s"]["radar"] == raw["sensors"]["radar"]["period_s"]
    assert a["radar"]["sigma0_m"] == raw["sensors"]["radar"]["sigma_m"]
    assert a["gnss"] == {"cn0_nominal_dbhz": 45.0, "agc_nominal_db": 0.0}  # los del simulador


def test_the_generalization_set_is_outside_the_training_ranges() -> None:
    for i in range(40):
        raw, _ = variants.sample_variant(GEN, i, "nominal", 0)
        assert not 10 <= raw["drone"]["max_airspeed_mps"] <= 23
        assert raw["sensors"]["gps"]["period_s"] in (0.2, 3.0)  # fuera de {0,5; 1; 2}
    assert variants.assign_splits(GEN, [{"name": f"v{i}", "family": "x"} for i in range(10)]) == {
        f"v{i}": "test" for i in range(10)
    }
