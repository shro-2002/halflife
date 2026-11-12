"""Tests for halflife.ledger (SQLite fact ledger + refit CLI)."""

import random
import sqlite3
from pathlib import Path

import pytest

from halflife.ledger import Ledger, main
from halflife.schemas import PRIOR_HALF_LIFE_DAYS, AnswerReport, VerdictLabel, VolatilityClass

FIXTURE = Path(__file__).parent / "fixtures" / "report.json"
VC = VolatilityClass


@pytest.fixture
def report() -> AnswerReport:
    return AnswerReport.model_validate_json(FIXTURE.read_text())


@pytest.fixture
def ledger(tmp_path):
    with Ledger(tmp_path / "ledger.sqlite") as led:
        yield led


def synthetic_report(template: AnswerReport, cls: VolatilityClass, outcomes, request_id=None) -> AnswerReport:
    """One searched claim per (age, changed) outcome, built from fixture claim c3 (searched + verdict)."""
    base = template.claims[2]
    claims = []
    for i, (age, changed) in enumerate(outcomes):
        label = VerdictLabel.CHANGED if changed else VerdictLabel.CURRENT
        claims.append(base.model_copy(update={
            "claim": base.claim.model_copy(update={"id": f"s{i}", "volatility_class": cls, "is_past_event": False}),
            "risk": base.risk.model_copy(update={"age_days": age}),
            "verdict": base.verdict.model_copy(update={"label": label}),
        }))
    return template.model_copy(update={"claims": claims, "bifrost_request_id": request_id})


def test_record_stores_claims_and_verifications(ledger, report):
    ledger.record(report, model="m1", virtual_key="vk1")
    n_claims = ledger.conn.execute("SELECT COUNT(*) FROM claims").fetchone()[0]
    labels = dict(ledger.conn.execute(
        "SELECT c.text, v.label FROM verifications v JOIN claims c ON c.id = v.claim_id").fetchall())
    assert n_claims == 6  # every claim, including unsearched price and timeless
    assert sorted(labels.values()) == ["changed", "current", "current", "unverifiable"]
    changed = ledger.conn.execute("SELECT label, changed FROM verifications ORDER BY id").fetchall()
    assert ("unverifiable", None) in changed and ("changed", 1) in changed and ("current", 0) in changed


def test_outcomes_exclude_unverifiable_and_past_events(ledger, report):
    ledger.record(report, model="m1", virtual_key="vk1")
    assert ledger.outcomes(VC.SOFTWARE_VERSION) == [(135.0, True)]
    assert ledger.outcomes(VC.OFFICE_HOLDER) == [(135.0, False)]
    assert ledger.outcomes(VC.RATE_OR_STATISTIC) == []  # unverifiable
    assert ledger.outcomes(VC.LAW_OR_REGULATION) == []  # is_past_event


def test_record_same_request_id_is_idempotent(ledger, report):
    rep = report.model_copy(update={"bifrost_request_id": "req-1"})
    ledger.record(rep, model="m", virtual_key=None)
    ledger.record(rep, model="m", virtual_key=None)
    assert ledger.conn.execute("SELECT COUNT(*) FROM verifications").fetchone()[0] == 4


def test_half_lives_fall_back_to_priors(ledger):
    hl = ledger.half_lives()
    assert VC.TIMELESS not in hl
    assert hl == {cls: (h, "prior_guess") for cls, h in PRIOR_HALF_LIFE_DAYS.items()}


def test_refit_updates_class_params_and_returns_old_new(ledger, report):
    rng = random.Random(0)
    outcomes = [(a, rng.random() < 1 - 2 ** (-a / 60.0)) for a in (rng.uniform(15, 240) for _ in range(150))]
    ledger.record(synthetic_report(report, VC.SOFTWARE_VERSION, outcomes), model="m", virtual_key="v")
    rows = {r.volatility_class: r for r in ledger.refit(min_outcomes=20)}
    sv = rows[VC.SOFTWARE_VERSION]
    assert (sv.old_half_life_days, sv.old_source) == (120.0, "prior_guess")
    assert sv.new_half_life_days is not None and sv.new_half_life_days < 120.0  # truth is 60
    assert sv.n == 150 and sv.n_changed == sum(c for _, c in outcomes)
    assert ledger.half_lives()[VC.SOFTWARE_VERSION] == (pytest.approx(sv.new_half_life_days), "fitted")
    again = {r.volatility_class: r for r in ledger.refit(min_outcomes=20)}[VC.SOFTWARE_VERSION]
    assert again.old_source == "fitted" and again.old_half_life_days == pytest.approx(sv.new_half_life_days)


def test_refit_respects_min_outcomes(ledger, report):
    ledger.record(synthetic_report(report, VC.PRICE, [(100.0, True)] * 5), model="m", virtual_key="v")
    rows = {r.volatility_class: r for r in ledger.refit(min_outcomes=6)}
    assert rows[VC.PRICE].new_half_life_days is None and rows[VC.PRICE].n == 5
    assert ledger.half_lives()[VC.PRICE] == (240.0, "prior_guess")
    assert ledger.conn.execute("SELECT COUNT(*) FROM class_params").fetchone()[0] == 0
    rows = {r.volatility_class: r for r in ledger.refit(min_outcomes=5)}
    assert rows[VC.PRICE].new_half_life_days is not None


def test_stale_rates_aggregate(ledger, report):
    ledger.record(report, model="m1", virtual_key="vk1")  # verified 3 (1 changed), 1 unverifiable
    ledger.record(synthetic_report(report, VC.PRICE, [(10.0, True), (10.0, True)]), model="m2", virtual_key=None)
    ledger.record(synthetic_report(report, VC.PRICE, [(10.0, False)]), model="m1", virtual_key="vk1")
    rows = ledger.stale_rates()
    assert rows == [
        {"model": "m1", "virtual_key": "vk1", "verified": 4, "changed": 1, "rate": 0.25},
        {"model": "m2", "virtual_key": None, "verified": 2, "changed": 2, "rate": 1.0},
    ]
    by_model = {r["model"]: r for r in ledger.stale_rates(group_by=("model",))}
    assert by_model["m1"]["verified"] == 4


def test_stale_rates_rejects_unknown_columns(ledger):
    with pytest.raises(ValueError):
        ledger.stale_rates(group_by=("model; DROP TABLE claims",))


def test_sql_injection_text_round_trips(ledger, report):
    nasty = "Robert'); DROP TABLE claims; -- \"quoted\" ; '' "
    c0 = report.claims[0]
    rep = report.model_copy(update={"claims": [c0.model_copy(update={
        "claim": c0.claim.model_copy(update={"text": nasty, "span": nasty, "subject": nasty})})]})
    ledger.record(rep, model=nasty, virtual_key=nasty)
    assert ledger.conn.execute("SELECT text, span, subject FROM claims").fetchone() == (nasty, nasty, nasty)
    assert ledger.stale_rates()[0]["model"] == nasty


def test_cli_refit_prints_table(tmp_path, report, capsys):
    db = tmp_path / "cli.sqlite"
    with Ledger(db) as led:
        led.record(synthetic_report(report, VC.OFFICE_HOLDER, [(500.0, False)] * 3), model="m", virtual_key=None)
    assert main(["refit", "--db", str(db), "--min", "3"]) == 0
    out = capsys.readouterr().out
    assert "office_holder" in out and "900.0 (prior_guess)" in out
    assert sqlite3.connect(db).execute("SELECT source FROM class_params").fetchall() == [("fitted",)]
