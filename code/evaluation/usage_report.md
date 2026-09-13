# Usage Report

## Model Providers and Names
- **None** — This solution uses deterministic Python with no LLM calls for the final dataset run.

## Token Usage
| Metric | Value |
|---|---|
| Model calls | 0 |
| Input tokens | 0 |
| Output tokens | 0 |
| Total tokens | 0 |
| Avg tokens per request | 0 |
| Estimated total cost | $0.0000 |
| Estimated cost per request | $0.0000 |

## Notes
- Receipt image extraction was performed offline using Claude Vision; results were persisted to `code/image_amounts.py` and committed as static data.
- The final `output.csv` run is fully deterministic: `python code/main.py` reads CSVs from `dataset/` and writes `output.csv` with no external API calls.
- Total runtime for 250 requests: ~2-3 seconds on a standard laptop.
