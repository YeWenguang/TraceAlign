"""Shared experiment configuration helpers for the clean artifact release."""

import argparse
import os
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "runs"


MODELS = {
    "gemini_2_5_flash": "gemini-2.5-flash",
    "gemini_2_5_pro": "gemini-2.5-pro",
    "gemini_2_5_flash_lite": "gemini-2.5-flash-lite",
    "gemini_2_0_flash": "gemini-2.0-flash",
    "gemini_1_5_flash": "gemini-1.5-flash",
    "qwen_plus": "qwen-plus-2025-12-01",
    "qwen_plus_2025_01": "qwen-plus-2025-01-25",
    "deepseek_chat": "deepseek-chat",
    "qwen2_5_coder": "qwen2.5-coder-32b-instruct",
    "gemini_3_pro": "gemini-3-pro-preview",
    "qwen3_coder_30b": "qwen3-coder-30b-a3b-instruct",
    "qwen2_5_coder_siliconflow": "Qwen/Qwen2.5-Coder-32B-Instruct",
}

DATASET_NAMES = {
    "APPS": "apps",
    "HumanEval+": "humaneval_plus",
    "LiveCodeBench": "livecodebench",
    "MBPP+": "mbpp_plus",
}

METHOD_NAMES = {
    "intervenor": "intervenor",
    "mapcoder": "mapcoder",
    "selfdebug": "selfdebug",
    "selfrepair": "selfrepair",
}


def get_model_name(model_key=None):
    if model_key is None:
        model_key = os.environ.get("MODEL_NAME", "gemini_2_5_flash")
    return MODELS.get(model_key, model_key)


def get_output_path(method, dataset, model_key=None, base_dir=None):
    if model_key is None:
        model_key = os.environ.get("MODEL_NAME", "gemini_2_5_flash")
    if base_dir is None:
        base_dir = DEFAULT_OUTPUT_DIR

    method_lower = METHOD_NAMES.get(method.lower(), method.lower())
    dataset_lower = DATASET_NAMES.get(dataset, dataset.lower().replace("+", "_plus"))
    filename = f"experiment_results_{method_lower}_{dataset_lower}_{model_key}.jsonl"
    return str(Path(base_dir) / filename)


def add_output_suffix(path, suffix=None):
    if not suffix:
        return path

    root, ext = os.path.splitext(path)
    return f"{root}_{suffix}{ext}"


def parse_args():
    parser = argparse.ArgumentParser(description="Code Generation Baseline Runner")

    parser.add_argument(
        "--model",
        type=str,
        default=os.environ.get("MODEL_NAME", "gemini_2_5_flash"),
        choices=list(MODELS.keys()),
        help=f"Model key. Choices: {', '.join(MODELS.keys())}",
    )

    parser.add_argument(
        "--output-dir",
        type=str,
        default=str(DEFAULT_OUTPUT_DIR),
        help="Directory for output JSONL files",
    )

    parser.add_argument(
        "--start-index",
        type=int,
        default=0,
        help="Inclusive dataset start index",
    )

    parser.add_argument(
        "--end-index",
        type=int,
        default=None,
        help="Exclusive dataset end index",
    )

    parser.add_argument(
        "--num-shards",
        type=int,
        default=1,
        help="Split the run into N shards",
    )

    parser.add_argument(
        "--shard-id",
        type=int,
        default=0,
        help="Current shard id, 0-based",
    )

    parser.add_argument(
        "--output-suffix",
        type=str,
        default=None,
        help="Optional suffix appended to the output filename",
    )

    parser.add_argument(
        "--max-loops",
        type=int,
        default=None,
        help="Override the default maximum repair loops",
    )

    parser.add_argument(
        "--resume-file",
        type=str,
        default=None,
        help="Resume from an existing output JSONL file",
    )

    return parser.parse_args()


def setup_config(method, dataset):
    args = parse_args()

    if args.num_shards < 1:
        raise ValueError("--num-shards must be at least 1")
    if args.shard_id < 0 or args.shard_id >= args.num_shards:
        raise ValueError("--shard-id must satisfy 0 <= shard-id < num-shards")
    if args.end_index is not None and args.end_index < args.start_index:
        raise ValueError("--end-index must be greater than or equal to --start-index")

    os.environ["MODEL_NAME"] = args.model
    model_name = get_model_name(args.model)

    if args.resume_file:
        output_file = args.resume_file
        print(f"[Config] Resume file: {output_file}")
    else:
        output_file = get_output_path(method, dataset, args.model, args.output_dir)
        suffix = args.output_suffix
        if suffix is None and args.num_shards > 1:
            suffix = f"shard{args.shard_id}of{args.num_shards}"
        output_file = add_output_suffix(output_file, suffix)

    print(f"[Config] Model: {model_name}")
    print(f"[Config] Output file: {output_file}")
    print(f"[Config] Start index: {args.start_index}")
    if args.end_index is not None:
        print(f"[Config] End index: {args.end_index}")
    if args.num_shards > 1:
        print(f"[Config] Shard: {args.shard_id + 1}/{args.num_shards}")

    return model_name, output_file, args
