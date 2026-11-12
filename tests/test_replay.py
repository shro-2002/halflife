"""Replay mode (public hosting): recorded examples, saved audit, daily live-check cap. Offline."""

import pytest
from fastapi.testclient import TestClient

import halflife.api as api
from halflife import replay
from halflife.schemas import AnswerReport


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("HALFLIFE_REPLAY", "1")
    monkeypatch.setenv("HALFLIFE_LIVE_CHECKS_PER_DAY", "2")
    monkeypatch.delenv("HALFLIFE_API_KEY", raising=False)
    monkeypatch.delenv("HALFLIFE_DEMO_MODE", raising=False)  # independent of the local .env
    monkeypatch.setattr(api, "RATE_LIMIT_PER_MIN", 100)
    api._hits.clear()
    api._fails.clear()
    calls = []

    async def fake_check(answer, **_):
        calls.append(answer)
        return AnswerReport.model_validate_json(open("tests/fixtures/report.json").read())

    monkeypatch.setattr(api, "check_answer", fake_check)
    with TestClient(api.app) as c:
        c.calls = calls
        yield c


def test_example_answers_are_served_recorded_without_any_check(client):
    for answer in replay.EXAMPLE_ANSWERS.values():
        r = client.post("/v1/check", json={"answer": "  " + answer + " "})
        assert r.status_code == 200 and r.json()["recorded"] is True
    assert client.calls == []  # no model or search call, no cap used
    assert client.get("/v1/mode").json()["live_checks_remaining_today"] == 2


def test_other_answers_are_live_until_the_daily_cap(client):
    for i in range(2):
        r = client.post("/v1/check", json={"answer": f"Some new claim {i}."})
        assert r.status_code == 200 and r.json()["recorded"] is False
    r = client.post("/v1/check", json={"answer": "One more claim."})
    assert r.status_code == 429 and r.json()["detail"]["code"] == "DAILY_LIVE_CAP"
    assert len(client.calls) == 2
    assert client.get("/v1/mode").json() == {"replay": True, "live_checks_per_day": 2,
                                              "live_checks_remaining_today": 0, "demo_mode": False}


def test_saved_audit_is_served_and_marked_recorded(client):
    r = client.get("/v1/gateway/summary")
    assert r.status_code == 200 and r.json()["recorded"] is True and len(r.json()["rows"]) == 4


def test_cap_resets_on_a_new_utc_day():
    cap = replay.DailyCap()
    assert cap.try_take(1) and not cap.try_take(1)
    from datetime import date
    cap.day = date(2000, 1, 1)
    assert cap.try_take(1)


def test_replay_off_means_no_cap_and_live_summary(monkeypatch):
    monkeypatch.delenv("HALFLIFE_REPLAY", raising=False)
    assert replay.enabled() is False
