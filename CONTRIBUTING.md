# Contributing

## Setup

```bash
uv sync
make test        # offline suite: fake model and fake search, no keys or network
```

Live tests (`@pytest.mark.live`) need a running Bifrost (`make bifrost && make setup`) and real keys in `.env`:

```bash
uv run pytest -q -m live
```

## Rules

- **Evidence only.** A verdict may rest only on text Tavily returned; quotes are checked verbatim in code
  (`halflife/verify.py`). Do not loosen that check to make a case pass.
- **Measured numbers only.** Any figure in docs or the UI must come from a file under `results/` with a reproduce
  command. `make eval` regenerates the detector tables from saved raw data without spending credits.
- **Fail open.** Search, model or parsing failures are recorded in the report; they never break a check.
- **Do not tune prompts against `eval/cases.jsonl`.** It is the held-out labelled set; labels are frozen at the eval
  date (2026-11-12). If a prompt changes, rerun the evaluation once and say so in the results README.
- **Stock Bifrost only.** Use public APIs and headers; no forks, no Go plugins. Verify new Bifrost or Tavily calls
  against the live docs (see `docs/SPIKE.md`).
- Secrets live in `.env` (git-ignored). Never log keys.

## Layout

| Path | What |
|---|---|
| `halflife/extract.py`, `verify.py`, `risk.py`, `fit.py`, `pipeline.py` | check pipeline |
| `halflife/gateway/` | audit, demo seeding, experimental TTL proxy, MCP tool |
| `halflife/clients/` | Bifrost client, Tavily-via-relay client, gateway setup, fakes |
| `eval/` | labelled cases, time-travel dataset, evaluation scripts |
| `results/` | recorded runs (each with a README) |

Commits follow Conventional Commits (`feat:`, `fix:`, `docs:` ...).
