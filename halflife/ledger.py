"""Fact ledger: every checked claim and its verification outcome, in SQLite.

Outcomes (age_days, changed) feed the per-class half-life fit (halflife.fit). Unverifiable
verdicts are stored (changed = NULL) but never used for fitting; dated past events are excluded
from fitting too (they do not decay).

CLI: uv run python -m halflife.ledger refit [--db PATH] [--min N]
"""

import argparse
import json
import sqlite3
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from halflife.fit import fit_half_life
from halflife.schemas import PRIOR_HALF_LIFE_DAYS, AnswerReport, VerdictLabel, VolatilityClass

DEFAULT_MIN_OUTCOMES = 20
STALE_RATE_COLUMNS = ("model", "virtual_key")  # allowlist: identifiers cannot be bound as parameters
CHANGED_BY_LABEL = {VerdictLabel.CHANGED: 1, VerdictLabel.CURRENT: 0, VerdictLabel.UNVERIFIABLE: None}

SCHEMA = """
CREATE TABLE IF NOT EXISTS claims (
    id TEXT PRIMARY KEY,
    text TEXT NOT NULL,
    span TEXT NOT NULL,
    volatility_class TEXT NOT NULL,
    subject TEXT,
    explicit_date TEXT,
    is_past_event INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS verifications (
    id INTEGER PRIMARY KEY,
    claim_id TEXT NOT NULL REFERENCES claims(id),
    checked_at TEXT NOT NULL,
    age_days REAL NOT NULL,
    age_basis TEXT NOT NULL,
    label TEXT NOT NULL CHECK (label IN ('current', 'changed', 'unverifiable')),
    changed INTEGER CHECK (changed IN (0, 1)),
    answer_request_id TEXT,
    model TEXT,
    virtual_key TEXT,
    rank_basis TEXT,
    p_stale REAL,
    p_outdated_model REAL
);
CREATE TABLE IF NOT EXISTS class_params (
    volatility_class TEXT PRIMARY KEY,
    half_life_days REAL NOT NULL,
    source TEXT NOT NULL CHECK (source IN ('prior_guess', 'fitted')),
    n INTEGER NOT NULL,
    n_changed INTEGER NOT NULL,
    fitted_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_verifications_claim_id ON verifications(claim_id);
CREATE INDEX IF NOT EXISTS idx_claims_volatility_class ON claims(volatility_class);
"""


@dataclass(frozen=True)
class RefitRow:
    volatility_class: VolatilityClass
    old_half_life_days: float
    old_source: str
    new_half_life_days: float | None  # None: fewer than min_outcomes, class_params left unchanged
    n: int
    n_changed: int


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _utc_iso(ts: datetime) -> str:
    return (ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)).astimezone(timezone.utc).isoformat()


class Ledger:
    def __init__(self, path: Path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(path)
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.executescript(SCHEMA)

    def __enter__(self) -> "Ledger":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def close(self) -> None:
        self.conn.close()

    def record(self, report: AnswerReport, *, model: str | None, virtual_key: str | None) -> None:
        """Store every claim; one verification row per searched claim with a verdict.

        Claim rows are keyed by answer (bifrost_request_id, else a fresh uuid) + claim id, so
        recording the same gateway request twice is a no-op.
        """
        answer_key = report.bifrost_request_id or uuid.uuid4().hex
        checked_at = _utc_iso(report.checked_at)
        with self.conn:
            for cr in report.claims:
                c = cr.claim
                row_id = f"{answer_key}:{c.id}"
                inserted = self.conn.execute(
                    "INSERT OR IGNORE INTO claims (id, text, span, volatility_class, subject, explicit_date,"
                    " is_past_event, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (row_id, c.text, c.span, c.volatility_class.value, c.subject,
                     c.explicit_date.isoformat() if c.explicit_date else None, int(c.is_past_event), _now()),
                ).rowcount
                if not inserted or not cr.searched or cr.verdict is None:
                    continue
                self.conn.execute(
                    "INSERT INTO verifications (claim_id, checked_at, age_days, age_basis, label, changed,"
                    " answer_request_id, model, virtual_key, rank_basis, p_stale, p_outdated_model)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (row_id, checked_at, cr.risk.age_days, cr.risk.age_basis.value, cr.verdict.label.value,
                     CHANGED_BY_LABEL[cr.verdict.label], report.bifrost_request_id, model, virtual_key,
                     cr.risk.rank_basis, cr.risk.p_stale, c.p_outdated_model),
                )

    def outcomes(self, volatility_class: VolatilityClass) -> list[tuple[float, bool]]:
        """(age_days, changed) for fitting: unverifiable rows and past events excluded."""
        rows = self.conn.execute(
            "SELECT v.age_days, v.changed FROM verifications v JOIN claims c ON c.id = v.claim_id"
            " WHERE c.volatility_class = ? AND v.changed IS NOT NULL AND c.is_past_event = 0"
            " ORDER BY v.id",
            (volatility_class.value,),
        ).fetchall()
        return [(age, bool(changed)) for age, changed in rows]

    def half_lives(self) -> dict[VolatilityClass, tuple[float, str]]:
        """Half-life in use per class: fitted value if stored, else the prior guess. Timeless excluded."""
        stored = {cls: (h, src) for cls, h, src in
                  self.conn.execute("SELECT volatility_class, half_life_days, source FROM class_params")}
        return {cls: stored.get(cls.value, (prior, "prior_guess")) for cls, prior in PRIOR_HALF_LIFE_DAYS.items()}

    def refit(self, min_outcomes: int = DEFAULT_MIN_OUTCOMES) -> list[RefitRow]:
        """Fit every class with >= min_outcomes outcomes and store it; one row per non-timeless class."""
        current = self.half_lives()
        rows = []
        with self.conn:
            for cls, prior in PRIOR_HALF_LIFE_DAYS.items():
                obs = [(a, c) for a, c in self.outcomes(cls) if a > 0]  # the fit ignores age <= 0
                old_h, old_src = current[cls]
                n_changed = sum(changed for _, changed in obs)
                if len(obs) < min_outcomes:
                    rows.append(RefitRow(cls, old_h, old_src, None, len(obs), n_changed))
                    continue
                fit = fit_half_life(obs, prior_half_life_days=prior)
                self.conn.execute(
                    "INSERT OR REPLACE INTO class_params (volatility_class, half_life_days, source, n, n_changed,"
                    " fitted_at) VALUES (?, ?, 'fitted', ?, ?, ?)",
                    (cls.value, fit.half_life_days, fit.n, fit.n_changed, _now()),
                )
                rows.append(RefitRow(cls, old_h, old_src, fit.half_life_days, fit.n, fit.n_changed))
        return rows

    def stale_rates(self, group_by: Sequence[str] = STALE_RATE_COLUMNS) -> list[dict]:
        """Per group: verified (current or changed), changed, rate = changed / verified."""
        cols = list(group_by)
        bad = [c for c in cols if c not in STALE_RATE_COLUMNS]
        if bad or not cols:
            raise ValueError(f"group_by must be a non-empty subset of {STALE_RATE_COLUMNS}, got {group_by!r}")
        sel = ", ".join(cols)
        rows = self.conn.execute(
            f"SELECT {sel}, COUNT(changed), COALESCE(SUM(changed), 0) FROM verifications"
            f" GROUP BY {sel} ORDER BY {sel}"
        ).fetchall()
        out = []
        for row in rows:
            verified, changed = row[-2], row[-1]
            out.append({**dict(zip(cols, row)), "verified": verified, "changed": changed,
                        "rate": changed / verified if verified else None})
        return out


def _format_refit(rows: list[RefitRow]) -> str:
    lines = [f"{'class':<20} {'old h (source)':<24} {'new h':>9} {'n':>5} {'n_changed':>9}"]
    for r in rows:
        new = f"{r.new_half_life_days:.1f}" if r.new_half_life_days is not None else "-"
        old = f"{r.old_half_life_days:.1f} ({r.old_source})"
        lines.append(f"{r.volatility_class.value:<20} {old:<24} {new:>9} {r.n:>5} {r.n_changed:>9}")
    return "\n".join(lines)


def import_fit(ledger: "Ledger", summary_path: Path) -> list[str]:
    """Seed class_params from the J0.5 time-travel fit (results/.../summary.json `half_lives`)."""
    fits = json.loads(summary_path.read_text())["half_lives"]
    done = []
    with ledger.conn:
        for cls, f in fits.items():
            ledger.conn.execute(
                "INSERT OR REPLACE INTO class_params (volatility_class, half_life_days, source, n, n_changed, fitted_at)"
                " VALUES (?, ?, 'fitted', ?, ?, ?)", (cls, float(f["fitted_days"]), int(f["n"]), int(f["n_changed"]), _now()))
            done.append(f"{cls}: {f['fitted_days']} d (n={f['n']})")
    return done


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m halflife.ledger")
    sub = parser.add_subparsers(dest="command", required=True)
    refit_p = sub.add_parser("refit", help="refit per-class half-lives from stored outcomes")
    refit_p.add_argument("--db", type=Path, default=None, help="ledger path (default: settings db_path)")
    refit_p.add_argument("--min", type=int, default=DEFAULT_MIN_OUTCOMES, dest="min_outcomes")
    imp = sub.add_parser("import-fit", help="seed half-lives from the time-travel fit (J0.5 summary.json)")
    imp.add_argument("summary", type=Path)
    imp.add_argument("--db", type=Path, default=None)
    args = parser.parse_args(argv)
    db = args.db
    if db is None:
        from halflife.config import load_settings  # deferred: loads .env

        db = load_settings().db_path
    with Ledger(db) as ledger:
        if args.command == "import-fit":
            print("\n".join(import_fit(ledger, args.summary)))
        else:
            print(_format_refit(ledger.refit(min_outcomes=args.min_outcomes)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
