from unittest.mock import patch

from app.core.config import Settings


def test_default_llm_model_is_groq_qwen():
    with patch.dict("os.environ", {}, clear=True):
        settings = Settings(_env_file=None)
    assert settings.llm_model == "qwen/qwen3.8-27b"
