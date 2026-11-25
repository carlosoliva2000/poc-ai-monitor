"""El constructor de matrices usa los activos de **cada variante** (no los de referencia):

uv run --project ai-module-py --group train pytest tools/training/tests/test_features_builder.py
"""

import math
from pathlib import Path

import features as builder
import numpy as np
import pytest
import yaml

from ai_module.situation.features import FEATURES

variants = pytest.importorskip("variants")


def test_each_variant_is_measured_with_its_own_drone_and_sensors(tmp_path: Path) -> None:
    manifest = yaml.safe_load(
        (variants.DEFAULT_MANIFEST.parent / "e7b-v2.yaml").read_text(encoding="utf-8")
    )
    out = variants.build(manifest | {"dataset": "tiny"}, tmp_path, workers=1, n=4)
    seen = set()
    for folder in sorted((out / "variants").iterdir()):
        assets = yaml.safe_load((folder / "assets.yaml").read_text(encoding="utf-8"))
        x, _, _ = builder.variant_matrix(folder)
        col = {name: x[:, FEATURES.index(name)] for name in FEATURES}
        ok = ~np.isnan(col["wind_est_mps"]) & ~np.isnan(col["wind_est_over_limit"])
        assert ok.any()
        ratio = col["wind_est_mps"][ok] / col["wind_est_over_limit"][ok]
        assert np.allclose(
            ratio[col["wind_est_mps"][ok] > 0.5], assets["drone"]["wind_limit_mps"], rtol=2e-3
        )
        period = assets["periods_s"]["radar"]
        age = col["age_radar"] / col["age_radar_p"]
        assert np.allclose(age[col["age_radar_p"] > 0], period, rtol=1e-3)
        seen.add(assets["drone"]["wind_limit_mps"])
    assert len(seen) > 1  # variantes distintas, límites distintos
    assert math.isfinite(sum(seen))
