import pytest

from app.core.config import get_settings


def _get_fresh_settings(monkeypatch, **env):
    managed_keys = {
        "APP_ENV",
        "CHECKPOINT_BACKEND",
        "CHECKPOINT_DIR",
        "CHECKPOINT_POSTGRES_URL",
        "CHECKPOINT_REDIS_URL",
        "ENABLE_EMOTION2VEC",
        "EMOTION2VEC_MODEL_DIR",
        "EMOTION2VEC_SAMPLE_RATE",
    }
    for key in managed_keys:
        monkeypatch.delenv(key, raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)

    get_settings.cache_clear()
    try:
        return get_settings()
    finally:
        get_settings.cache_clear()


def test_settings_expose_model_provider_defaults():
    settings = get_settings()
    assert settings.llm_provider in {"litellm"}
    assert settings.llm_model
    assert isinstance(settings.enable_rag, bool)


def test_settings_expose_checkpoint_contract_defaults(monkeypatch):
    settings = _get_fresh_settings(monkeypatch)
    assert settings.app_env == "development"
    assert settings.checkpoint_backend == "memory"
    assert settings.checkpoint_dir


def test_settings_reject_memory_checkpoint_backend_in_production(monkeypatch):
    with pytest.raises(ValueError, match="Persistent checkpoint backend is required"):
        _get_fresh_settings(
            monkeypatch,
            APP_ENV="production",
            CHECKPOINT_BACKEND="memory",
        )


def test_settings_expose_emotion2vec_defaults(monkeypatch):
    settings = _get_fresh_settings(monkeypatch)
    assert settings.enable_emotion2vec is False
    assert settings.emotion2vec_model_dir == ""
    assert settings.emotion2vec_sample_rate == 16000


def test_settings_read_emotion2vec_env(monkeypatch):
    settings = _get_fresh_settings(
        monkeypatch,
        ENABLE_EMOTION2VEC="true",
        EMOTION2VEC_MODEL_DIR="/tmp/emotion2vec",
        EMOTION2VEC_SAMPLE_RATE="22050",
    )
    assert settings.enable_emotion2vec is True
    assert settings.emotion2vec_model_dir == "/tmp/emotion2vec"
    assert settings.emotion2vec_sample_rate == 22050
