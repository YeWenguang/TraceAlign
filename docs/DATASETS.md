# Included Datasets

The clean artifact keeps only the benchmark files needed by the paper's main TraceAlign experiments.

## APPS

- File: `datasets/APPS/data/selected150.jsonl`
- Evaluator: `datasets/APPS/test_one_solution.py`

## HumanEval+

- File: `datasets/human_eval_plus/data/test-00000-of-00001-5973903632b82d40.parquet`
- Evaluator: `datasets/human_eval_plus/execution.py`

## MBPP+

- File: `datasets/MBPP/Plus/test-00000-of-00001-d5781c9c51e02795.parquet`
- Evaluator: `datasets/MBPP/execution.py`

## LiveCodeBench

- Files: `datasets/LiveCodeBench/data/test6.part00.jsonl`, `datasets/LiveCodeBench/data/test6.part01.jsonl`
- Evaluator: `datasets/LiveCodeBench/single_eval.py`
- Supporting runtime: `datasets/LiveCodeBench/lcb_runner/`
- Loader behavior: `runners/livecodebench.py` automatically reads the single-file layout (`test6.jsonl`) or the sharded layout (`test6.part*.jsonl`)

No cached downloads, `.git` history, logs, or result files are included in the release directory.
