"""Las listas de entradas permitidas por faceta (E7b, paso 2b):

uv run --project ai-module-py --group train pytest tools/training/tests/test_allowed.py
"""

import re

from allowed import ABSOLUTE_OK, ALLOWED, RELATIVE_LEGACY

from ai_module.situation.features import FEATURES, RELATIVE
from poc_contracts.states import FACETS


def test_every_facet_has_a_list_and_every_entry_exists_and_is_justified() -> None:
    assert set(ALLOWED) == set(FACETS)
    for facet, entries in ALLOWED.items():
        names = [name for name, _ in entries]
        assert names and len(names) == len(set(names)), facet
        assert set(names) <= set(FEATURES), (facet, set(names) - set(FEATURES))
        assert all(why.strip() for _, why in entries), facet


def test_only_relative_features_or_the_listed_absolute_ones_are_allowed() -> None:
    for facet, entries in ALLOWED.items():
        for name, _ in entries:
            ok = name in RELATIVE or name in RELATIVE_LEGACY or name in ABSOLUTE_OK
            assert ok, f"{facet}: {name} is absolute and not in ABSOLUTE_OK"
    # el viento ya no entra en m/s absolutos en ninguna faceta (v3: «notable» es 0,4 × límite)
    assert not {n for e in ALLOWED.values() for n, _ in e} & {"wind_est_mps", "station_wind_mps"}


def test_no_allowed_feature_carries_the_nominal_of_the_receiver_or_a_raw_coordinate() -> None:
    for entries in ALLOWED.values():
        for name, _ in entries:
            assert name not in ("cn0_dbhz", "agc_db", "airspeed_mps", "ground_speed_mps")
            assert not re.search(r"(^|_)(x|y|lat|lon)(_|$)", name)
