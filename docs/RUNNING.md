# Running Guide

## One-Click Entry

Use the unified launcher from the artifact root:

```bash
bash run.sh
```

This defaults to `HumanEval+`.

## Dataset Options

```bash
bash run.sh --dataset apps
bash run.sh --dataset humaneval_plus
bash run.sh --dataset mbpp_plus
bash run.sh --dataset livecodebench
bash run.sh --dataset all
```

## Passing Through Original Runner Args

Any extra arguments are forwarded to the internal runner:

```bash
bash run.sh --dataset apps --model qwen_plus --start-index 0 --end-index 20
bash run.sh --dataset livecodebench --model gemini_2_5_flash --output-suffix smoke_test
```

## Output Location

Outputs are created only when a run starts:

- `runs/experiment_results_tracealign_apps_<model>.jsonl`
- `runs/experiment_results_tracealign_humaneval_plus_<model>.jsonl`
- `runs/experiment_results_tracealign_mbpp_plus_<model>.jsonl`
- `runs/experiment_results_tracealign_livecodebench_<model>.jsonl`

The artifact ships without any pre-generated result files.
