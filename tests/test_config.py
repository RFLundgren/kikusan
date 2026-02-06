"""Tests for configuration validation."""

import os
import pytest
from unittest.mock import patch

from kikusan.config import Config


class TestConfigValidation:
    """Test configuration value validation."""

    def test_negative_cookie_retry_delay_raises_error(self):
        """Test that negative cookie retry delay raises ValueError."""
        with patch.dict(os.environ, {"KIKUSAN_COOKIE_RETRY_DELAY": "-1.5"}):
            with pytest.raises(ValueError, match="KIKUSAN_COOKIE_RETRY_DELAY must be non-negative"):
                Config.from_env()

    def test_zero_cookie_retry_delay_is_valid(self):
        """Test that zero cookie retry delay is allowed."""
        with patch.dict(os.environ, {"KIKUSAN_COOKIE_RETRY_DELAY": "0"}):
            config = Config.from_env()
            assert config.cookie_retry_delay == 0.0

    def test_positive_cookie_retry_delay_is_valid(self):
        """Test that positive cookie retry delay is allowed."""
        with patch.dict(os.environ, {"KIKUSAN_COOKIE_RETRY_DELAY": "2.5"}):
            config = Config.from_env()
            assert config.cookie_retry_delay == 2.5

    def test_negative_unavailable_cooldown_uses_zero(self, caplog):
        """Test that negative unavailable cooldown logs warning and uses 0."""
        with patch.dict(os.environ, {"KIKUSAN_UNAVAILABLE_COOLDOWN_HOURS": "-100"}):
            config = Config.from_env()
            assert config.unavailable_cooldown_hours == 0
            assert "KIKUSAN_UNAVAILABLE_COOLDOWN_HOURS is negative" in caplog.text

    def test_zero_unavailable_cooldown_is_valid(self):
        """Test that zero unavailable cooldown is allowed (disabled)."""
        with patch.dict(os.environ, {"KIKUSAN_UNAVAILABLE_COOLDOWN_HOURS": "0"}):
            config = Config.from_env()
            assert config.unavailable_cooldown_hours == 0

    def test_positive_unavailable_cooldown_is_valid(self):
        """Test that positive unavailable cooldown is allowed."""
        with patch.dict(os.environ, {"KIKUSAN_UNAVAILABLE_COOLDOWN_HOURS": "168"}):
            config = Config.from_env()
            assert config.unavailable_cooldown_hours == 168

    def test_web_port_below_1_raises_error(self):
        """Test that web port below 1 raises ValueError."""
        with patch.dict(os.environ, {"KIKUSAN_WEB_PORT": "0"}):
            with pytest.raises(ValueError, match="KIKUSAN_WEB_PORT must be between 1 and 65535"):
                Config.from_env()

    def test_web_port_above_65535_raises_error(self):
        """Test that web port above 65535 raises ValueError."""
        with patch.dict(os.environ, {"KIKUSAN_WEB_PORT": "70000"}):
            with pytest.raises(ValueError, match="KIKUSAN_WEB_PORT must be between 1 and 65535"):
                Config.from_env()

    def test_web_port_1_is_valid(self):
        """Test that web port 1 is valid (lower bound)."""
        with patch.dict(os.environ, {"KIKUSAN_WEB_PORT": "1"}):
            config = Config.from_env()
            assert config.web_port == 1

    def test_web_port_65535_is_valid(self):
        """Test that web port 65535 is valid (upper bound)."""
        with patch.dict(os.environ, {"KIKUSAN_WEB_PORT": "65535"}):
            config = Config.from_env()
            assert config.web_port == 65535

    def test_web_port_8000_is_valid(self):
        """Test that web port 8000 is valid (default value)."""
        with patch.dict(os.environ, {}, clear=True):
            # Clear all env vars to use defaults
            with patch.dict(os.environ, {}):
                config = Config.from_env()
                assert config.web_port == 8000

    def test_default_values_are_valid(self):
        """Test that all default values pass validation."""
        with patch.dict(os.environ, {}, clear=True):
            # This should not raise any errors
            config = Config.from_env()
            assert config.cookie_retry_delay == 1.0
            assert config.unavailable_cooldown_hours == 168
            assert config.web_port == 8000
