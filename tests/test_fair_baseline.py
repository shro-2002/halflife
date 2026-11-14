"""Fair baseline for budget curves: random order among cases the extractor sent to search. Offline."""

from eval.run import GRID, avg_curve, time_sensitive_scores


def _row(label: str, outcome: str, url: str) -> dict:
    return {"label": label, "outcome": outcome, "flagged": outcome == "changed", "source_url": url}


ROWS = ([_row("stale", "changed", f"s{i}") for i in range(4)] + [_row("current", "current", f"c{i}") for i in range(4)]
        + [_row("timeless", "not_searched", f"t{i}") for i in range(8)])


def test_fair_baseline_spends_budget_on_searched_cases_first() -> None:
    curve = avg_curve(ROWS, time_sensitive_scores(ROWS), 200, 1)
    half = GRID.index(0.5)  # 8 of 16 cases = every searched case
    assert curve[half] == 1.0
    assert abs(curve[GRID.index(0.25)] - 0.5) < 0.1  # 4 of 8 searched cases, in random order


def test_fair_baseline_beats_blind_random_when_non_searched_cases_exist() -> None:
    fair = avg_curve(ROWS, time_sensitive_scores(ROWS), 200, 1)
    blind = avg_curve(ROWS, [0.0] * len(ROWS), 200, 1)
    assert fair[GRID.index(0.5)] > blind[GRID.index(0.5)] + 0.3
