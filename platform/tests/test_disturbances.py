import math

import pytest

from helpers import scenario_config
from platform_app.generator.disturbances import (
    is_hijacked,
    spoof_offset,
    spoof_offset_rate,
    wind_at,
)


def test_base_wind_outside_episodes() -> None:
    w = wind_at(10.0, scenario_config("wind").wind)
    assert (w.speed_mps, w.gust_mps, w.from_deg) == (2.0, 3.5, 300.0)


def test_episode_ramps_up_holds_and_ramps_down() -> None:
    wind = scenario_config("wind").wind  # 95–150 s, rampa 10 s, 12 m/s, racha 16, del 350°
    assert wind_at(95.0, wind).speed_mps == pytest.approx(2.0)  # arranca en la velocidad base
    assert wind_at(100.0, wind).speed_mps == pytest.approx(7.0)  # a media rampa
    assert wind_at(120.0, wind) == wind_at(120.0, wind)
    full = wind_at(120.0, wind)
    assert (full.speed_mps, full.gust_mps, full.from_deg) == (12.0, 16.0, 350.0)
    assert wind_at(145.0, wind).speed_mps == pytest.approx(7.0)
    assert wind_at(150.5, wind).speed_mps == pytest.approx(2.0)
    assert wind_at(150.5, wind).from_deg == 300.0


def test_wind_from_north_pushes_south() -> None:
    from platform_app.generator.disturbances import Wind

    east, north = Wind(10.0, 12.0, 0.0).vector()
    assert east == pytest.approx(0.0, abs=1e-9)
    assert north == pytest.approx(-10.0)
    east, north = Wind(5.0, 5.0, 270.0).vector()  # del oeste: empuja al este
    assert (east, north) == (pytest.approx(5.0), pytest.approx(0.0, abs=1e-9))


def test_spoof_offset_grows_and_vanishes_at_the_end() -> None:
    spoof = scenario_config("spoofing").spoofing  # 168–222 s, 1,5 m/s hacia 45°
    assert spoof_offset(100.0, spoof) == (0.0, 0.0)
    assert spoof_offset(168.0, spoof) == (0.0, 0.0)
    x, y = spoof_offset(198.0, spoof)  # 30 s -> 45 m
    assert math.hypot(x, y) == pytest.approx(45.0)
    assert x == pytest.approx(y)
    assert spoof_offset(222.0, spoof) == (0.0, 0.0)  # el desfase desaparece de golpe
    rate = spoof_offset_rate(200.0, spoof)
    assert math.hypot(*rate) == pytest.approx(1.5)
    assert spoof_offset_rate(230.0, spoof) == (0.0, 0.0)
    assert spoof_offset(10.0, None) == (0.0, 0.0)


def test_hijack_window_is_half_open_and_open_ended_when_no_end() -> None:
    hijack = scenario_config("hijack").hijack
    assert not is_hijacked(334.9, hijack)
    assert is_hijacked(335.0, hijack)
    assert is_hijacked(379.9, hijack)
    assert not is_hijacked(380.0, hijack)
    assert not is_hijacked(1.0, None)
    open_ended = hijack.model_copy(update={"end_s": None})
    assert is_hijacked(1e6, open_ended)
