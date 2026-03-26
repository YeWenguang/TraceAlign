# TraceAlign

This directory contains the full system code and benchmark data needed to run TraceAlign on the four datasets used in the paper:

- `APPS`
- `HumanEval+`
- `MBPP+`
- `LiveCodeBench`

## Directory Layout

- `components/`: core TraceAlign modules
- `utils/`: execution tracing, parsing, and repair helpers
- `llm/`: API client configuration
- `datasets/`: bundled benchmark subsets and evaluation adapters
- `runners/`: internal dataset-specific runners
- `config/`: API config template
- `docs/`: reproduction notes
- `run.py` / `run.sh`: unified one-click launcher

## Quick Start

1. Create a Python environment and install dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

2. Configure your API:

```bash
cp config/api.env.example config/api.env
```

Then edit `config/api.env` and fill in:

- `TRACEALIGN_API_KEY`
- `TRACEALIGN_BASE_URL` if your endpoint is OpenAI-compatible but not the official OpenAI endpoint

3. Run with the unified launcher:

```bash
bash run.sh
```

The default command runs `HumanEval+`. You can switch datasets with one flag:

```bash
bash run.sh --dataset apps
bash run.sh --dataset mbpp_plus
bash run.sh --dataset livecodebench
bash run.sh --dataset all
```

You can still pass the original runner arguments through the same command:

```bash
bash run.sh --dataset humaneval_plus --model gemini_2_5_flash --start-index 0 --end-index 10
```

## Notes

- The artifact uses relative paths only; there are no machine-specific absolute paths in the release directory.
- API credentials are not hard-coded. The system reads them from `config/api.env` or standard environment variables.
- Generated logs and JSONL outputs are created under `runs/` on demand.
- The internal dataset runners are preserved under `runners/`, but users only need the unified launcher.
- The bundled LiveCodeBench input is stored as `datasets/LiveCodeBench/data/test6.part*.jsonl` shards to stay within GitHub file size limits. The runner loads these shards automatically.

More detail is available in `docs/RUNNING.md` and `docs/DATASETS.md`.
