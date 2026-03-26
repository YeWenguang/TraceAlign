#!/usr/bin/env python3
"""Unified launcher for the clean TraceAlign artifact release."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_ENV_FILE = PROJECT_ROOT / "config" / "api.env"
RUNNERS = {
    "apps": PROJECT_ROOT / "runners" / "apps.py",
    "humaneval_plus": PROJECT_ROOT / "runners" / "humaneval_plus.py",
    "mbpp_plus": PROJECT_ROOT / "runners" / "mbpp_plus.py",
    "livecodebench": PROJECT_ROOT / "runners" / "livecodebench.py",
}


def load_env_file(path: Path) -> None:
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def normalize_dataset(name: str) -> str:
    token = name.lower().replace("-", "").replace("_", "").replace("+", "plus")
    aliases = {
        "apps": "apps",
        "humaneval": "humaneval_plus",
        "humanevalplus": "humaneval_plus",
        "mbpp": "mbpp_plus",
        "mbppplus": "mbpp_plus",
        "livecodebench": "livecodebench",
        "lcb": "livecodebench",
        "all": "all",
    }
    if token not in aliases:
        raise ValueError(f"Unsupported dataset: {name}")
    return aliases[token]


def ensure_api_config() -> None:
    api_key = os.environ.get("TRACEALIGN_API_KEY") or os.environ.get("OPENAI_API_KEY")
    if api_key:
        return
    raise SystemExit(
        "API is not configured. Create config/api.env from config/api.env.example "
        "or export TRACEALIGN_API_KEY / OPENAI_API_KEY first."
    )


def run_single(dataset: str, runner_args: list[str]) -> int:
    runner_path = RUNNERS[dataset]
    command = [sys.executable, str(runner_path), *runner_args]
    print(f"[Launcher] Running {dataset} via {' '.join(command)}")
    completed = subprocess.run(command, cwd=PROJECT_ROOT, env=os.environ.copy())
    return completed.returncode


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Unified TraceAlign launcher")
    parser.add_argument(
        "--dataset",
        default="humaneval_plus",
        help="apps | humaneval_plus | mbpp_plus | livecodebench | all",
    )
    parser.add_argument(
        "--env-file",
        default=str(DEFAULT_ENV_FILE),
        help="Path to the API env file. Defaults to config/api.env.",
    )
    parser.add_argument(
        "--list-datasets",
        action="store_true",
        help="Print supported datasets and exit.",
    )

    args, runner_args = parser.parse_known_args(argv)

    if args.list_datasets:
        print("apps")
        print("humaneval_plus")
        print("mbpp_plus")
        print("livecodebench")
        print("all")
        return 0

    env_file = Path(args.env_file)
    if not env_file.is_absolute():
        env_file = PROJECT_ROOT / env_file
    load_env_file(env_file)
    ensure_api_config()

    dataset = normalize_dataset(args.dataset)
    datasets_to_run = list(RUNNERS) if dataset == "all" else [dataset]

    for item in datasets_to_run:
        return_code = run_single(item, runner_args)
        if return_code != 0:
            return return_code
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
