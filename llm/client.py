"""OpenAI-compatible client helpers used by the clean artifact release."""

from __future__ import annotations

import logging
import os
import time
from pathlib import Path


logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ENV_FILE = PROJECT_ROOT / "config" / "api.env"
DEFAULT_MODEL_KEY = "gemini_2_5_flash"

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


def load_api_env(env_file: Path = DEFAULT_ENV_FILE) -> None:
    if not env_file.exists():
        return

    for raw_line in env_file.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def get_model_name(model_key=None):
    load_api_env()
    if model_key is None:
        model_key = os.environ.get("MODEL_NAME", DEFAULT_MODEL_KEY)
    return MODELS.get(model_key, model_key)


def get_api_provider():
    load_api_env()
    explicit_provider = os.environ.get("API_PROVIDER") or os.environ.get("TRACEALIGN_API_PROVIDER")
    if explicit_provider:
        return explicit_provider

    model_key = os.environ.get("MODEL_NAME", DEFAULT_MODEL_KEY)
    if model_key.startswith("qwen"):
        return "qwen"
    if model_key.startswith("gemini"):
        return "gemini"
    if model_key.startswith("deepseek"):
        return "deepseek"
    return "custom"


def get_client():
    load_api_env()
    from openai import OpenAI

    api_key = os.environ.get("TRACEALIGN_API_KEY") or os.environ.get("OPENAI_API_KEY")
    base_url = os.environ.get("TRACEALIGN_BASE_URL") or os.environ.get("OPENAI_BASE_URL")

    if not api_key:
        raise RuntimeError(
            "No API key configured. Please create config/api.env from "
            "config/api.env.example or export TRACEALIGN_API_KEY."
        )

    client_kwargs = {"api_key": api_key}
    if base_url:
        client_kwargs["base_url"] = base_url
    return OpenAI(**client_kwargs)


def call_openai_api(prompt, model=None, max_retries=5):
    """Call an OpenAI-compatible chat endpoint and return text with token counts."""
    if model is None:
        model = get_model_name()

    client = get_client()
    last_error = None

    for retry_count in range(max_retries + 1):
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": "You are a helpful assistant."},
                    {"role": "user", "content": prompt},
                ],
            )

            result_text = response.choices[0].message.content
            prompt_tokens = 0
            completion_tokens = 0
            if response.usage:
                prompt_tokens = response.usage.prompt_tokens
                completion_tokens = response.usage.completion_tokens
            return result_text, prompt_tokens, completion_tokens
        except Exception as exc:
            last_error = exc
            if retry_count == max_retries:
                break
            wait_seconds = min(5 * (retry_count + 1), 20)
            print(f"API call failed, retrying in {wait_seconds}s: {exc}")
            time.sleep(wait_seconds)

    logger.error("API call failed after retries: %s", last_error)
    return None, 0, 0


def call_openai_api2(prompt, model=None, max_retries=2):
    return call_openai_api(prompt, model, max_retries)


load_api_env()
