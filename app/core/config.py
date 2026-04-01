"""应用配置。

当前阶段不引入数据库，也不依赖复杂配置中心。
本模块只做一件事：把模型调用和告警 webhook 相关配置收口，
避免后续从阿里云百炼切到本地模型时要全局搜索替换。
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache

from dotenv import load_dotenv


load_dotenv()

ALLOWED_APP_ENVS = {"development", "test", "staging", "production"}
ALLOWED_CHECKPOINT_BACKENDS = {"memory", "file", "postgres", "redis"}
ALLOWED_TTS_PROVIDERS = {"dashscope", "edge_tts"}


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    return int(raw)


def _env_str(name: str, default: str) -> str:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip()


@dataclass(frozen=True)
class Settings:
    """统一配置对象。

    这里刻意保持轻量，避免为了一个最小骨架引入过多依赖。
    后续如果配置变复杂，可以平滑切换到 pydantic-settings。
    """

    app_name: str = field(
        default_factory=lambda: _env_str(
            "APP_NAME", "面向高校学生心理风险早期识别与转介辅助的多智能体协同系统"
        )
    )
    app_env: str = field(default_factory=lambda: _env_str("APP_ENV", "development").lower())
    app_host: str = field(default_factory=lambda: _env_str("APP_HOST", "0.0.0.0"))
    app_port: int = field(default_factory=lambda: _env_int("APP_PORT", 8000))

    # 模型抽象层默认使用 LiteLLM，底层走 OpenAI-compatible 风格配置。
    llm_provider: str = field(default_factory=lambda: _env_str("LLM_PROVIDER", "litellm"))
    llm_model: str = field(default_factory=lambda: _env_str("LLM_MODEL", "openai/qwen3.5-plus"))
    llm_api_key: str = field(
        default_factory=lambda: _env_str("LLM_API_KEY", os.getenv("BAILIAN_API_KEY", ""))
    )
    llm_base_url: str = field(
        default_factory=lambda: _env_str(
            "LLM_BASE_URL",
            "https://dashscope.aliyuncs.com/compatible-mode/v1",
        )
    )
    llm_timeout_seconds: int = field(
        default_factory=lambda: _env_int("LLM_TIMEOUT_SECONDS", 30)
    )
    llm_verbose: bool = field(default_factory=lambda: _env_bool("LITELLM_VERBOSE", False))
    tts_enabled: bool = field(default_factory=lambda: _env_bool("TTS_ENABLED", True))
    tts_provider: str = field(
        default_factory=lambda: _env_str("TTS_PROVIDER", "dashscope").lower()
    )
    tts_api_key: str = field(
        default_factory=lambda: _env_str(
            "TTS_API_KEY",
            os.getenv("BAILIAN_API_KEY", os.getenv("LLM_API_KEY", "")),
        )
    )
    tts_model: str = field(default_factory=lambda: _env_str("TTS_MODEL", "qwen-tts-latest"))
    tts_base_url: str = field(
        default_factory=lambda: _env_str("TTS_BASE_URL", "https://dashscope.aliyuncs.com/api/v1")
    )
    tts_timeout_seconds: int = field(
        default_factory=lambda: _env_int("TTS_TIMEOUT_SECONDS", 60)
    )
    tts_qwen_voice: str = field(
        default_factory=lambda: _env_str(
            "TTS_QWEN_VOICE",
            _env_str("TTS_VOICE", "Serena"),
        )
    )
    tts_qwen_language_type: str = field(
        default_factory=lambda: _env_str("TTS_QWEN_LANGUAGE_TYPE", "Chinese")
    )
    tts_voice: str = field(
        default_factory=lambda: _env_str("TTS_VOICE", "zh-CN-XiaoxiaoNeural")
    )
    tts_rate: str = field(default_factory=lambda: _env_str("TTS_RATE", "+0%"))
    tts_volume: str = field(default_factory=lambda: _env_str("TTS_VOLUME", "+0%"))
    tts_output_format: str = field(
        default_factory=lambda: _env_str(
            "TTS_OUTPUT_FORMAT",
            "audio-24khz-48kbitrate-mono-mp3",
        )
    )

    # 高风险闭环先走 mock webhook，后续替换成真实系统即可。
    counselor_alert_webhook: str = field(
        default_factory=lambda: _env_str(
            "COUNSELOR_ALERT_WEBHOOK", "mock://counselor-alert"
        )
    )
    ragflow_base_url: str = field(default_factory=lambda: _env_str("RAGFLOW_BASE_URL", "http://127.0.0.1"))
    ragflow_api_key: str = field(default_factory=lambda: _env_str("RAGFLOW_API_KEY", ""))
    ragflow_dataset_id: str = field(default_factory=lambda: _env_str("RAGFLOW_DATASET_ID", ""))
    ragflow_timeout_seconds: int = field(
        default_factory=lambda: _env_int("RAGFLOW_TIMEOUT_SECONDS", 10)
    )
    enable_rag: bool = field(default_factory=lambda: _env_bool("ENABLE_RAG", False))

    checkpoint_backend: str = field(
        default_factory=lambda: _env_str("CHECKPOINT_BACKEND", "memory").lower()
    )
    checkpoint_dir: str = field(
        default_factory=lambda: _env_str(
            "CHECKPOINT_DIR", ".langgraph-checkpoints"
        )
    )
    checkpoint_postgres_url: str = field(
        default_factory=lambda: _env_str("CHECKPOINT_POSTGRES_URL", "")
    )
    checkpoint_redis_url: str = field(
        default_factory=lambda: _env_str("CHECKPOINT_REDIS_URL", "")
    )
    enable_emotion2vec: bool = field(
        default_factory=lambda: _env_bool("ENABLE_EMOTION2VEC", True)
    )
    emotion2vec_model_dir: str = field(
        default_factory=lambda: _env_str("EMOTION2VEC_MODEL_DIR", "")
    )
    emotion2vec_sample_rate: int = field(
        default_factory=lambda: _env_int("EMOTION2VEC_SAMPLE_RATE", 16000)
    )

    def __post_init__(self) -> None:
        if self.app_env not in ALLOWED_APP_ENVS:
            raise ValueError(
                f"APP_ENV must be one of {sorted(ALLOWED_APP_ENVS)}, got {self.app_env!r}."
            )

        if self.checkpoint_backend not in ALLOWED_CHECKPOINT_BACKENDS:
            raise ValueError(
                "CHECKPOINT_BACKEND must be one of "
                f"{sorted(ALLOWED_CHECKPOINT_BACKENDS)}, got {self.checkpoint_backend!r}."
            )

        if self.app_env in {"staging", "production"} and self.checkpoint_backend == "memory":
            raise ValueError(
                "Persistent checkpoint backend is required for staging/production."
            )

        if self.checkpoint_backend == "file" and not self.checkpoint_dir:
            raise ValueError("CHECKPOINT_DIR is required when CHECKPOINT_BACKEND=file.")

        if self.checkpoint_backend == "postgres" and not self.checkpoint_postgres_url:
            raise ValueError(
                "CHECKPOINT_POSTGRES_URL is required when CHECKPOINT_BACKEND=postgres."
            )

        if self.checkpoint_backend == "redis" and not self.checkpoint_redis_url:
            raise ValueError(
                "CHECKPOINT_REDIS_URL is required when CHECKPOINT_BACKEND=redis."
            )

        if self.tts_provider not in ALLOWED_TTS_PROVIDERS:
            raise ValueError(
                f"TTS_PROVIDER must be one of {sorted(ALLOWED_TTS_PROVIDERS)}, got {self.tts_provider!r}."
            )

        if self.emotion2vec_sample_rate <= 0:
            raise ValueError("EMOTION2VEC_SAMPLE_RATE must be a positive integer.")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """缓存配置，避免每次请求重复解析环境变量。"""

    return Settings()
