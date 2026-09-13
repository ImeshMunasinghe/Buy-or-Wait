# Buy or Wait? — Financial Decision Agent

## Setup
No external dependencies required. Uses only Python standard library (Python 3.10+).

## Run
```bash
python code/main.py
```

This reads from `dataset/` and writes `output.csv` in the repo root.

## Output Format
`output.csv` with columns: `request_id, amount_safe_to_pay, affordability_status, recommended_payment_method, payment_plan, earliest_date_for_full_payment, spending_changes_needed, decision_explanation`

## Architecture
- `code/image_amounts.py` — receipt amounts extracted from `dataset/media/images/`
- `code/loader.py` — loads profiles, events, exchange rates, payment options, messages; builds per-user financial context
- `code/forecast.py` — cash-flow projection engine
- `code/decide.py` — deterministic decision rules (full/partial/installments/wait + spending changes)
- `code/main.py` — pipeline orchestration

## Design Decisions
- All financial arithmetic is deterministic Python (no LLM involved in calculations)
- LLM is used only for receipt image extraction (done offline, results in `image_amounts.py`)
- Variable daily spending is disabled; only confirmed income and recurring essential expenses are projected
- Salary override from employer messages is respected
