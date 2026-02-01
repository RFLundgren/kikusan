"""Tests for explore section in cron configuration."""

import textwrap
from pathlib import Path

import pytest
import yaml

from kikusan.cron.config import (
    CronConfig,
    ExploreConfig,
    load_config,
    validate_country_code,
)


class TestExploreConfigParsing:
    """Test parsing of explore entries in cron.yaml."""

    def _write_yaml(self, tmp_path: Path, content: str) -> Path:
        """Helper to write YAML content to a temp file."""
        config_path = tmp_path / "cron.yaml"
        config_path.write_text(textwrap.dedent(content))
        return config_path

    def test_charts_config(self, tmp_path):
        """Test parsing a charts explore entry."""
        config_path = self._write_yaml(tmp_path, """\
            explore:
              us-charts:
                type: charts
                country: US
                sync: true
                schedule: "0 6 * * *"
        """)

        config = load_config(config_path)
        assert "us-charts" in config.explore
        entry = config.explore["us-charts"]
        assert isinstance(entry, ExploreConfig)
        assert entry.name == "us-charts"
        assert entry.type == "charts"
        assert entry.country == "US"
        assert entry.sync is True
        assert entry.schedule == "0 6 * * *"
        assert entry.params == ""

    def test_mood_config(self, tmp_path):
        """Test parsing a mood explore entry."""
        config_path = self._write_yaml(tmp_path, """\
            explore:
              chill-vibes:
                type: mood
                params: "ggMPOg1uX1J"
                sync: false
                schedule: "0 12 * * 0"
        """)

        config = load_config(config_path)
        assert "chill-vibes" in config.explore
        entry = config.explore["chill-vibes"]
        assert entry.type == "mood"
        assert entry.params == "ggMPOg1uX1J"
        assert entry.sync is False
        assert entry.schedule == "0 12 * * 0"
        assert entry.country == "ZZ"  # default

    def test_charts_default_country(self, tmp_path):
        """Test charts entry defaults to ZZ for country."""
        config_path = self._write_yaml(tmp_path, """\
            explore:
              global-charts:
                type: charts
                sync: true
                schedule: "0 6 * * *"
        """)

        config = load_config(config_path)
        assert config.explore["global-charts"].country == "ZZ"

    def test_multiple_explore_entries(self, tmp_path):
        """Test parsing multiple explore entries."""
        config_path = self._write_yaml(tmp_path, """\
            explore:
              us-charts:
                type: charts
                country: US
                sync: true
                schedule: "0 6 * * *"
              gb-charts:
                type: charts
                country: GB
                sync: false
                schedule: "0 7 * * *"
              pop-moods:
                type: mood
                params: "ggMPOg1uX1J"
                sync: true
                schedule: "0 12 * * 0"
        """)

        config = load_config(config_path)
        assert len(config.explore) == 3
        assert "us-charts" in config.explore
        assert "gb-charts" in config.explore
        assert "pop-moods" in config.explore

    def test_explore_only_config(self, tmp_path):
        """Test config with only explore entries (no playlists or plugins)."""
        config_path = self._write_yaml(tmp_path, """\
            explore:
              us-charts:
                type: charts
                country: US
                sync: true
                schedule: "0 6 * * *"
        """)

        config = load_config(config_path)
        assert len(config.playlists) == 0
        assert len(config.plugins) == 0
        assert len(config.explore) == 1

    def test_explore_with_playlists(self, tmp_path):
        """Test config with both playlists and explore entries."""
        config_path = self._write_yaml(tmp_path, """\
            playlists:
              my-playlist:
                url: "https://music.youtube.com/playlist?list=PLtest"
                sync: true
                schedule: "5 4 * * *"
            explore:
              us-charts:
                type: charts
                country: US
                sync: true
                schedule: "0 6 * * *"
        """)

        config = load_config(config_path)
        assert len(config.playlists) == 1
        assert len(config.explore) == 1


class TestExploreConfigValidation:
    """Test validation of explore entries."""

    def _write_yaml(self, tmp_path: Path, content: str) -> Path:
        config_path = tmp_path / "cron.yaml"
        config_path.write_text(textwrap.dedent(content))
        return config_path

    def test_invalid_type(self, tmp_path):
        """Test that invalid explore type raises ValueError."""
        config_path = self._write_yaml(tmp_path, """\
            explore:
              bad-entry:
                type: invalid
                sync: true
                schedule: "0 6 * * *"
        """)

        with pytest.raises(ValueError, match="type must be 'charts' or 'mood'"):
            load_config(config_path)

    def test_missing_type(self, tmp_path):
        """Test that missing type raises ValueError."""
        config_path = self._write_yaml(tmp_path, """\
            explore:
              bad-entry:
                sync: true
                schedule: "0 6 * * *"
        """)

        with pytest.raises(ValueError, match="missing required field: type"):
            load_config(config_path)

    def test_missing_sync(self, tmp_path):
        """Test that missing sync raises ValueError."""
        config_path = self._write_yaml(tmp_path, """\
            explore:
              bad-entry:
                type: charts
                schedule: "0 6 * * *"
        """)

        with pytest.raises(ValueError, match="missing required field: sync"):
            load_config(config_path)

    def test_missing_schedule(self, tmp_path):
        """Test that missing schedule raises ValueError."""
        config_path = self._write_yaml(tmp_path, """\
            explore:
              bad-entry:
                type: charts
                sync: true
        """)

        with pytest.raises(ValueError, match="missing required field: schedule"):
            load_config(config_path)

    def test_mood_missing_params(self, tmp_path):
        """Test that mood type without params raises ValueError."""
        config_path = self._write_yaml(tmp_path, """\
            explore:
              bad-mood:
                type: mood
                sync: true
                schedule: "0 6 * * *"
        """)

        with pytest.raises(ValueError, match="missing required field: params"):
            load_config(config_path)

    def test_mood_empty_params(self, tmp_path):
        """Test that mood type with empty params raises ValueError."""
        config_path = self._write_yaml(tmp_path, """\
            explore:
              bad-mood:
                type: mood
                params: "   "
                sync: true
                schedule: "0 6 * * *"
        """)

        with pytest.raises(ValueError, match="params must be a non-empty string"):
            load_config(config_path)

    def test_invalid_country_code_lowercase(self, tmp_path):
        """Test that lowercase country code raises ValueError."""
        config_path = self._write_yaml(tmp_path, """\
            explore:
              bad-charts:
                type: charts
                country: us
                sync: true
                schedule: "0 6 * * *"
        """)

        with pytest.raises(ValueError, match="invalid country code"):
            load_config(config_path)

    def test_invalid_country_code_three_letters(self, tmp_path):
        """Test that 3-letter country code raises ValueError."""
        config_path = self._write_yaml(tmp_path, """\
            explore:
              bad-charts:
                type: charts
                country: USA
                sync: true
                schedule: "0 6 * * *"
        """)

        with pytest.raises(ValueError, match="invalid country code"):
            load_config(config_path)

    def test_invalid_cron_schedule(self, tmp_path):
        """Test that invalid cron schedule raises ValueError."""
        config_path = self._write_yaml(tmp_path, """\
            explore:
              bad-charts:
                type: charts
                sync: true
                schedule: "not a cron"
        """)

        with pytest.raises(ValueError, match="invalid cron schedule"):
            load_config(config_path)

    def test_invalid_name_characters(self, tmp_path):
        """Test that name with special characters raises ValueError."""
        config_path = self._write_yaml(tmp_path, """\
            explore:
              "bad name!":
                type: charts
                sync: true
                schedule: "0 6 * * *"
        """)

        with pytest.raises(ValueError, match="Invalid playlist name"):
            load_config(config_path)

    def test_sync_must_be_boolean(self, tmp_path):
        """Test that sync must be a boolean."""
        config_path = self._write_yaml(tmp_path, """\
            explore:
              bad-entry:
                type: charts
                sync: "yes"
                schedule: "0 6 * * *"
        """)

        with pytest.raises(ValueError, match="sync must be a boolean"):
            load_config(config_path)

    def test_explore_must_be_dict(self, tmp_path):
        """Test that explore section must be a dictionary."""
        config_path = self._write_yaml(tmp_path, """\
            explore:
              - type: charts
        """)

        with pytest.raises(ValueError, match="'explore' must be a dictionary"):
            load_config(config_path)

    def test_entry_must_be_dict(self, tmp_path):
        """Test that each explore entry must be a dictionary."""
        config_path = self._write_yaml(tmp_path, """\
            explore:
              bad-entry: "not a dict"
        """)

        with pytest.raises(ValueError, match="config must be a dictionary"):
            load_config(config_path)


class TestValidateCountryCode:
    """Test validate_country_code()."""

    def test_valid_us(self):
        validate_country_code("US", "test")

    def test_valid_gb(self):
        validate_country_code("GB", "test")

    def test_valid_zz(self):
        validate_country_code("ZZ", "test")

    def test_invalid_lowercase(self):
        with pytest.raises(ValueError, match="invalid country code"):
            validate_country_code("us", "test")

    def test_invalid_three_letters(self):
        with pytest.raises(ValueError, match="invalid country code"):
            validate_country_code("USA", "test")

    def test_invalid_one_letter(self):
        with pytest.raises(ValueError, match="invalid country code"):
            validate_country_code("U", "test")

    def test_invalid_numbers(self):
        with pytest.raises(ValueError, match="invalid country code"):
            validate_country_code("12", "test")

    def test_invalid_empty(self):
        with pytest.raises(ValueError, match="invalid country code"):
            validate_country_code("", "test")


class TestExploreConfigBackwardCompatibility:
    """Test that existing configs without explore still work."""

    def _write_yaml(self, tmp_path: Path, content: str) -> Path:
        config_path = tmp_path / "cron.yaml"
        config_path.write_text(textwrap.dedent(content))
        return config_path

    def test_config_without_explore(self, tmp_path):
        """Test that configs without explore section still load."""
        config_path = self._write_yaml(tmp_path, """\
            playlists:
              my-playlist:
                url: "https://music.youtube.com/playlist?list=PLtest"
                sync: true
                schedule: "5 4 * * *"
        """)

        config = load_config(config_path)
        assert len(config.playlists) == 1
        assert len(config.explore) == 0

    def test_empty_explore_section(self, tmp_path):
        """Test that empty explore section is handled."""
        config_path = self._write_yaml(tmp_path, """\
            playlists:
              my-playlist:
                url: "https://music.youtube.com/playlist?list=PLtest"
                sync: true
                schedule: "5 4 * * *"
            explore:
        """)

        # YAML parses empty value as None, which is not a dict
        # This should still work - playlists section is present
        config = load_config(config_path)
        assert len(config.explore) == 0
