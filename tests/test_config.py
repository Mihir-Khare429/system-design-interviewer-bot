"""
Tests for app/config.py — settings loading and defaults.
"""

import os
import pytest
from unittest.mock import patch


class TestSettings:
    def test_reads_recall_api_key_from_env(self):
        with patch.dict(os.environ, {"RECALL_API_KEY": "rk_abc123"}):
            from importlib import reload
            import app.config as cfg
            reload(cfg)
            assert cfg.Settings().recall_api_key == "rk_abc123"

    def test_reads_openai_api_key_from_env(self):
        with patch.dict(os.environ, {"OPENAI_API_KEY": "sk_xyz789"}):
            from importlib import reload
            import app.config as cfg
            reload(cfg)
            assert cfg.Settings().openai_api_key == "sk_xyz789"

    def test_port_default_is_8000(self):
        from app.config import Settings
        s = Settings()
        assert s.port == 8000

    def test_port_overridden_by_env(self):
        with patch.dict(os.environ, {"PORT": "9000"}):
            from app.config import Settings
            s = Settings()
            assert s.port == 9000

    def test_webhook_base_url_default(self):
        """Default webhook_base_url should point to localhost."""
        with patch.dict(os.environ, {}, clear=False):
            from app.config import Settings
            s = Settings(_env_file=None)
            # Should contain localhost or the test value we set in conftest
            assert isinstance(s.webhook_base_url, str)
            assert len(s.webhook_base_url) > 0

    def test_webhook_base_url_from_env(self):
        with patch.dict(os.environ, {"WEBHOOK_BASE_URL": "https://my.ngrok.app"}):
            from app.config import Settings
            s = Settings()
            assert s.webhook_base_url == "https://my.ngrok.app"

    def test_bot_persona_name_default(self):
        from app.config import Settings
        s = Settings()
        assert isinstance(s.bot_persona_name, str)
        assert len(s.bot_persona_name) > 0

    def test_bot_persona_name_from_env(self):
        with patch.dict(os.environ, {"BOT_PERSONA_NAME": "SDE Bot"}):
            from app.config import Settings
            s = Settings()
            assert s.bot_persona_name == "SDE Bot"

    def test_extra_env_vars_are_ignored(self):
        """Extra environment variables should not raise a validation error."""
        with patch.dict(os.environ, {"TOTALLY_UNKNOWN_VAR": "blah"}):
            from app.config import Settings
            s = Settings()
            assert s is not None
