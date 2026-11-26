"""API `/api/v1`: lectura por asset y flujo en directo.

Lo importante: cada asset da solo lo suyo, la verdad del ejercicio no sale por los assets, el flujo
no pierde ni duplica mensajes (también al reanudar) y lo que llega por la API es lo que pasó por
el bus.
"""

import sys
import threading
import time
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sim_api_helpers import LiveServer, SseStream

from platform_app.app import create_app
from platform_app.paths import REPO_ROOT
from platform_app.sim_api.assets import ASSET_IDS, ASSET_OF_TYPE, message_types
from platform_app.sim_api.feed import Log
from poc_contracts.enums import EventType, FaultMode, SensorSource

LIFECYCLE = {"RunStarted", "RunReset", "RunFinished"}
INSTRUCTOR_ONLY = {
    "FaultInjected",
    "FaultCleared",
    "InstructorCommand",
    "ExerciseInjects",
    "InteractiveModeChanged",
}
WIND = {
    "command": "set_wind",
    "params": {"from_deg": 0, "speed_mps": 12, "ramp_s": 10, "duration_s": 60},
    "issued_by": "panel",
    "text": None,
}


@pytest.fixture
def client(runs_dir: Path) -> Iterator[TestClient]:
    with TestClient(create_app(runs_dir=runs_dir, run_clock=False)) as c:
        yield c


def player(client: TestClient):  # noqa: ANN201
    return client.app.state.player  # type: ignore[attr-defined]


def all_messages(client: TestClient, asset: str, **params: str) -> list[dict]:
    out: list[dict] = []
    since = -1
    while True:
        page = client.get(
            f"/api/v1/assets/{asset}/messages", params={"since": since, "limit": 500, **params}
        ).json()
        out += page["messages"]
        since = page["next"]
        if not page["has_more"]:
            return out


def run_with_injects(client: TestClient, seconds: float = 120.0) -> None:
    """`nominal` en modo interactivo con un fallo y un comando del instructor a mitad."""
    p = player(client)
    p.load("nominal")
    p.set_interactive(True)
    p.play()
    p.advance(40.0)
    p.fault(SensorSource.RADAR, FaultMode.MUTE, True)
    p.advance(20.0)
    client.post("/api/v1/instructor/commands", json=WIND)
    p.advance(seconds - 60.0)


def test_inventory_is_empty_until_a_scenario_is_loaded(client: TestClient) -> None:
    body = client.get("/api/v1/assets").json()
    assert body == {"scenario_loaded": False, "assets": []}
    assert client.get("/api/v1/assets/d1").status_code == 404
    player(client).load("demo")
    assets = {a["id"]: a for a in client.get("/api/v1/assets").json()["assets"]}
    assert list(assets) == list(ASSET_IDS)
    assert assets["d1"]["config"]["wind_limit_mps"] == 12.0
    assert assets["radar-1"]["config"]["max_range_m"] == 6000.0
    assert assets["gcs-1"]["config"]["controller_id"] == "GCS-1"
    assert client.get("/api/v1/assets/nope").status_code == 404


def test_inventory_never_carries_the_exercise(client: TestClient) -> None:
    player(client).load("demo")
    text = client.get("/api/v1/assets").text.lower()
    for forbidden in ("spoof", "hijack", "wind_episode", "fault", "emitter", "episode"):
        assert forbidden not in text


def test_each_asset_gives_only_its_own_and_never_the_exercise(client: TestClient) -> None:
    run_with_injects(client)
    for asset in ASSET_IDS:
        messages = all_messages(client, asset)
        assert messages, asset
        allowed = set(message_types(asset)) | LIFECYCLE
        assert {m["type"] for m in messages} <= allowed, asset
        assert not {m["type"] for m in messages} & INSTRUCTOR_ONLY
        assert all(m["asset_id"] == asset for m in messages)
    state = client.get("/api/v1/assets/radar-1/state").json()
    assert set(state["last"]) <= set(message_types("radar-1"))


def test_a_muted_source_is_silent_on_its_asset(client: TestClient) -> None:
    run_with_injects(client)
    radar = [m for m in all_messages(client, "radar-1") if m["type"] == "TrackUpdated"]
    assert radar and all(not (40.0 <= m["sim_time"] < 60.0) for m in radar)


def test_api_equals_the_bus(client: TestClient) -> None:
    """Por asset, lo que da la API es lo que pasó por el bus (id, tipo, tiempos y payload)."""
    run_with_injects(client)
    bus = {e.event_id: e for e in player(client).bus.timeline.all() if e.type in ASSET_OF_TYPE}
    seen: set[str] = set()
    for asset in ASSET_IDS:
        messages = [m for m in all_messages(client, asset) if m["type"] not in LIFECYCLE]
        assert [m["seq"] for m in messages] == sorted(m["seq"] for m in messages)
        for m in messages:
            e = bus[m["id"]]
            assert ASSET_OF_TYPE[e.type] == asset
            assert (m["type"], m["sim_time"], m["data"]) == (e.type.value, e.sim_time, e.payload)
            assert (m["time_utc"], m["received_utc"]) == (e.event_time, e.ingestion_time)
            assert m["subject"] == e.asset
            seen.add(m["id"])
    assert seen == set(bus)  # ni se pierde ni se inventa ningún evento


def test_pagination_walks_the_history_once(client: TestClient) -> None:
    run_with_injects(client)
    full = all_messages(client, "d1")
    seqs = [m["seq"] for m in full]
    assert seqs == list(range(seqs[0], seqs[0] + len(seqs)))  # consecutivos, sin repetir
    page = client.get("/api/v1/assets/d1/messages", params={"limit": 7}).json()
    assert len(page["messages"]) == 7 and page["has_more"]
    assert page["next"] == page["messages"][-1]["seq"]
    # con filtro por tipo, `next` avanza aunque la página salga vacía
    sparse = client.get(
        "/api/v1/assets/d1/messages", params={"types": "MissionCompleted", "limit": 5}
    ).json()
    assert [m["type"] for m in sparse["messages"]] in ([], ["MissionCompleted"])
    caught_up = client.get("/api/v1/assets/d1/messages", params={"since": full[-1]["seq"]}).json()
    assert caught_up["messages"] == [] and caught_up["next"] == full[-1]["seq"]
    assert not caught_up["has_more"]
    assert client.get("/api/v1/assets/d1/messages", params={"types": "Nope"}).status_code == 422
    assert client.get("/api/v1/assets/d1/messages", params={"run_id": "x"}).status_code == 404


def test_lifecycle_and_seq_survive_a_reset(client: TestClient) -> None:
    p = player(client)
    p.load("nominal")
    first_run = p.run_id
    p.run_to_end()
    before = all_messages(client, "gcs-1")
    assert before[0]["type"] == "RunStarted" and before[-1]["type"] == "RunFinished"
    assert "scenario" not in before[0]["data"] and before[0]["data"]["duration_s"] > 0
    p.reset()
    p.play()
    p.advance(20.0)
    now = all_messages(client, "gcs-1")  # la ejecución en curso
    assert now[0]["type"] == "RunStarted" and now[0]["run_id"] == p.run_id != first_run
    assert now[0]["seq"] > before[-1]["seq"] + 1  # RunReset en medio; el `seq` no se reinicia
    old = all_messages(client, "gcs-1", run_id=first_run)
    assert [m["type"] for m in old if m["type"] in LIFECYCLE] == [
        "RunStarted",
        "RunFinished",
        "RunReset",
    ]


def test_only_the_last_two_runs_are_kept(client: TestClient) -> None:
    p = player(client)
    ids = iter(["20261126-100000", "20261126-100001", "20261126-100002"])
    p._run_id_factory = lambda: next(ids)
    runs = []
    for _ in range(3):
        p.load("nominal")
        runs.append(p.run_id)
    assert client.get("/api/v1/assets/d1/messages", params={"run_id": runs[0]}).status_code == 404
    assert client.get("/api/v1/assets/d1/messages", params={"run_id": runs[1]}).status_code == 200


def test_log_trims_but_keeps_counting() -> None:
    log = Log(cap=3)
    for _ in range(5):
        log.add(lambda seq: _msg(seq))
    assert (log.first_available, log.last_seq) == (3, 5)
    assert [m.seq for m in log.read(0)] == [3, 4, 5]
    assert [m.seq for m in log.read(3)] == [4, 5]


def _msg(seq: int):  # noqa: ANN202
    from poc_contracts.sim_api import AssetMessage

    return AssetMessage(
        seq=seq, run_id="r", asset_id="d1", subject="d1", type="PositionUpdated", id=f"x{seq}",
        sim_time=0.0, time_utc="2026-10-20T10:00:00Z", received_utc="2026-10-20T10:00:00.000Z",
        data={},
    )  # fmt: skip


# --- Flujo en directo ----------------------------------------------------------------------------


def test_stream_has_no_loss_or_duplicates_and_resumes(runs_dir: Path) -> None:
    with LiveServer(runs_dir) as server:
        p = server.player
        p.load("nominal")
        p.play()
        live = SseStream(server.port, "/api/v1/assets/d1/stream")
        assert live.status == 200 and live.content_type.startswith("text/event-stream")
        p.advance(30.0)
        first = live.messages(20)
        assert [e.id for e in first] == [e.data["seq"] for e in first]
        # el cliente se corta tras 20 mensajes y reanuda con `Last-Event-ID`
        live.close()
        p.advance(30.0)
        resumed = SseStream(server.port, "/api/v1/assets/d1/stream",
                            {"Last-Event-ID": str(first[-1].id)})  # fmt: skip
        history = server.get("/api/v1/assets/d1/messages?since=-1&limit=10000")["messages"]
        want = [m["seq"] for m in history if m["seq"] > first[-1].id]
        got = [e.id for e in resumed.messages(len(want))]
        resumed.close()
        assert got == want
        # en directo desde el `seq` 2 (el 1 es `RunStarted`, anterior a la conexión): ni hueco ni
        # repetido
        assert [e.id for e in first] + got == [m["seq"] for m in history if m["seq"] >= 2]


def test_stream_replays_from_the_start_and_across_a_reset(runs_dir: Path) -> None:
    with LiveServer(runs_dir) as server:
        p = server.player
        p.load("nominal")
        p.play()
        p.advance(15.0)
        p.reset()
        p.play()
        p.advance(15.0)
        stream = SseStream(server.port, "/api/v1/assets/gcs-1/stream?since=-1")
        total = server.app.state.feed.logs["gcs-1"].last_seq
        events = [e for _, e in zip(range(total + 1), stream, strict=False)]
        stream.close()
        assert "gap" not in {e.event for e in events}  # `since=-1` es «desde el principio»
        got = [e for e in events if e.event == "message"]
        assert [e.id for e in got] == list(range(got[0].id, got[0].id + len(got)))
        assert [e.data["type"] for e in got if e.data["type"] in LIFECYCLE][:3] == [
            "RunStarted",
            "RunReset",
            "RunStarted",
        ]


def test_stream_sends_heartbeats_and_a_gap_when_the_cursor_is_gone(runs_dir: Path) -> None:
    with LiveServer(runs_dir) as server:
        p = server.player
        p.load("nominal")
        server.app.state.feed.logs["d1"].cap = 30
        p.play()
        p.advance(40.0)
        stream = SseStream(server.port, "/api/v1/assets/d1/stream?since=0")
        first = next(iter(stream))
        assert first.event == "gap" and first.data["requested"] == 0
        assert first.data["first_available"] > 1
        seen = {e.event for e, _ in zip(stream, range(40), strict=False)}
        stream.close()
        assert "heartbeat" in seen
        beat = SseStream(server.port, "/api/v1/assets/meteo-1/stream")
        hb = next(e for e in beat if e.event == "heartbeat")
        beat.close()
        assert hb.id is None and hb.data["status"] == "running"
        assert hb.data["sim_time"] == p.sim_time


def test_instructor_stream_is_separate(runs_dir: Path) -> None:
    with LiveServer(runs_dir) as server:
        p = server.player
        p.load("nominal")
        p.set_interactive(True)
        p.play()
        p.advance(5.0)
        p.fault(SensorSource.RADAR, FaultMode.MUTE, True)
        p.advance(1.0)  # el fallo se publica con el siguiente paso
        stream = SseStream(server.port, "/api/v1/instructor/stream?since=-1")
        count = server.app.state.feed.logs["instructor"].last_seq
        types = [e.data["type"] for e in stream.messages(count)]
        stream.close()
        assert {"RunStarted", "ExerciseInjects", "InteractiveModeChanged", "FaultInjected"} <= set(
            types
        )
        asset_stream = SseStream(server.port, "/api/v1/assets/radar-1/stream?since=-1")
        seen = {e.data["type"] for e in asset_stream.messages(2)}
        asset_stream.close()
        assert not seen & INSTRUCTOR_ONLY


def test_world_events_are_the_only_event_types_on_assets() -> None:
    assert set(ASSET_OF_TYPE) <= {
        t for t in EventType if t.value not in INSTRUCTOR_ONLY and not t.value.startswith("Sim")
    }


def test_a_worker_that_starts_before_the_exercise_retries_until_there_is_one(
    runs_dir: Path,
) -> None:
    """Sin escenario `/assets/{id}` da 404; el consumidor de referencia reintenta con su backoff."""
    sys.path.insert(0, str(REPO_ROOT / "tools" / "sim_api"))
    import consume  # noqa: PLC0415

    with LiveServer(runs_dir) as server:
        url = f"http://127.0.0.1:{server.port}"
        found: dict = {}
        worker = threading.Thread(
            target=lambda: found.update(consume.fetch_asset(url, "radar-1", base=0.05)), daemon=True
        )
        worker.start()
        time.sleep(0.4)
        assert worker.is_alive() and not found  # sigue esperando: no hay escenario
        server.player.load("nominal")
        worker.join(timeout=10)
        assert found["id"] == "radar-1" and found["config"]["max_range_m"] == 6000.0
        # un asset que no existe no se reintenta
        with pytest.raises(RuntimeError, match="404"):
            consume.fetch_asset(url, "nope", base=0.05)
