from fastapi.testclient import TestClient

from flypoker.main import app
from flypoker import main as live_main
from flypoker.models import EventEnvelope


def test_health_and_metrics_are_read_only():
    with TestClient(app) as client:
        assert client.get("/health/live").json() == {"status": "live"}
        metrics = client.get("/v1/metrics")
        assert metrics.status_code == 200
        assert "eventSequence" in metrics.json()


def test_websocket_reports_offline_without_verified_brain():
    with TestClient(app) as client:
        with client.websocket_connect("/v1/live/ws", headers={"origin": "http://localhost:3000"}) as socket:
            first = socket.receive_json()
            assert first["kind"] == "status"
            assert first["status"]["status"] == "offline"
            event = EventEnvelope(tournament_id="t", hand_id="h", sequence=1, type="test")
            wire = event.model_dump(mode="json", by_alias=True)
            assert {"schemaVersion", "tournamentId", "handId", "serverTime"}.issubset(wire)


def test_historical_replay_slug_resolves_its_own_tournament(monkeypatch):
    calls: list[tuple[str, str]] = []

    def hand_events(tournament_id: str, hand_id: str):
        calls.append((tournament_id, hand_id))
        return []

    monkeypatch.setattr(live_main.engine.store, "hand_events", hand_events)
    with TestClient(app) as client:
        response = client.get("/v1/replays/tourney-archive-hand-0042")
    assert response.status_code == 404
    assert calls == [("tourney-archive", "hand-0042")]
