"""El adaptador de la API al bus (lo que hará el mediador) reconstruye exactamente los eventos.

Sin servidor: el reproductor publica en un bus, el `Feed` los traduce al formato de cada asset y
los mensajes se entregan al adaptador en un orden mezclado (cada asset en el suyo, con sus
`heartbeat` verdaderos). Tiene que salir la misma lista de eventos del mundo, en el mismo orden.
"""

import random
import sys
from pathlib import Path

import pytest

from helpers import make_player, published_drafts
from platform_app.paths import REPO_ROOT
from platform_app.player import Player
from platform_app.sim_api.assets import ASSET_IDS
from platform_app.sim_api.feed import Feed
from poc_contracts.topics import topic_domain

sys.path.insert(0, str(REPO_ROOT / "tools" / "sim_api"))
from adapter import Lifecycle, Merger  # noqa: E402


def world(drafts: list[dict]) -> list[dict]:
    return [d for d in drafts if topic_domain(d["topic"]) in ("air", "env")]


def delivery(feed: Feed, rng: random.Random) -> list[tuple[str, str, dict]]:
    """Lo que recibiría un consumidor: cada asset en su orden, mezclados entre sí, y tras cada
    mensaje un `heartbeat` que promete lo que de verdad ocurre (lo siguiente no es anterior)."""
    queues: dict[str, list[tuple[str, str, dict]]] = {}
    for asset in ASSET_IDS:
        messages = feed.logs[asset].read(0)
        items: list[tuple[str, str, dict]] = []
        for i, m in enumerate(messages):
            items.append((asset, "message", m.model_dump(mode="json")))
            nxt = messages[i + 1].sim_time if i + 1 < len(messages) else m.sim_time
            beat = {"run_id": m.run_id, "status": "running", "sim_time": nxt, "speed": 1.0}
            items.append((asset, "heartbeat", beat))
        queues[asset] = items
    out: list[tuple[str, str, dict]] = []
    while any(queues.values()):
        asset = rng.choice([a for a, q in queues.items() if q])
        take = rng.randint(1, 6)
        out += queues[asset][:take]
        del queues[asset][:take]
    return out


def reconstruct(feed: Feed, seed: int) -> tuple[list[dict], list[str]]:
    merger = Merger()
    events: list[dict] = []
    lifecycle: list[str] = []
    released = []
    for asset, event, data in delivery(feed, random.Random(seed)):
        released += merger.feed(asset, event, data)
    released += merger.flush()
    for item in released:
        if isinstance(item, Lifecycle):
            lifecycle.append(item.kind)
        else:
            events.append(item.model_dump(mode="json"))
    return events, lifecycle


def drafts(events: list[dict]) -> list[dict]:
    return [{k: v for k, v in e.items() if k not in ("seq", "ingestion_time")} for e in events]


@pytest.fixture(scope="module")
def scenario_names(runs_dir: Path) -> list[str]:
    return sorted(p.name for p in runs_dir.iterdir() if (p / "events.jsonl").exists())


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_every_scenario_is_rebuilt_exactly(runs_dir: Path, scenario_names: list[str], seed: int):
    for name in scenario_names:
        player = make_player(runs_dir)
        feed = Feed(player.bus)
        player.load(name)
        player.run_to_end()
        events, lifecycle = reconstruct(feed, seed)
        expected = world(published_drafts(player))
        assert drafts(events) == expected, name
        assert lifecycle == ["RunStarted", "RunFinished"], name


def test_a_reset_in_the_middle_keeps_the_runs_apart(runs_dir: Path) -> None:
    player: Player = make_player(runs_dir)
    feed = Feed(player.bus)
    player.load("nominal")
    player.play()
    player.advance(20.0)
    first = world(published_drafts(player))
    player.reset()
    player.run_to_end()
    second = world(published_drafts(player))
    events, lifecycle = reconstruct(feed, seed=7)
    assert drafts(events) == first + second
    assert lifecycle == ["RunStarted", "RunReset", "RunStarted", "RunFinished"]
