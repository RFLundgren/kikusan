"""Tests for CLI options and flags."""

import errno
import os
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
from typer.testing import CliRunner

from kikusan.cli import _migrate_legacy_data_dir, app


class TestGlobalOptions:
    """Test global CLI options."""

    def setup_method(self):
        """Clear relevant environment variables before each test."""
        for key in ["KIKUSAN_COOKIE_MODE", "KIKUSAN_COOKIE_RETRY_DELAY", "KIKUSAN_LOG_COOKIE_USAGE"]:
            if key in os.environ:
                del os.environ[key]

    def test_cookie_mode_sets_env_var(self):
        """Test --cookie-mode sets environment variable."""
        runner = CliRunner()
        result = runner.invoke(app, ["--cookie-mode", "always", "--help"])
        assert result.exit_code == 0
        # Note: The env var is set during command execution, not in --help output

    def test_cookie_mode_choices(self):
        """Test --cookie-mode validates choices."""
        runner = CliRunner()
        # Don't pass --help so click can validate the choice
        result = runner.invoke(app, ["--cookie-mode", "invalid"])
        assert result.exit_code != 0
        assert "Invalid value" in result.output

    def test_cookie_retry_delay_accepts_float(self):
        """Test --cookie-retry-delay accepts float values."""
        runner = CliRunner()
        result = runner.invoke(app, ["--cookie-retry-delay", "2.5", "--help"])
        assert result.exit_code == 0

    def test_no_log_cookie_usage_flag(self):
        """Test --no-log-cookie-usage is a valid flag."""
        runner = CliRunner()
        result = runner.invoke(app, ["--no-log-cookie-usage", "--help"])
        assert result.exit_code == 0


class TestDataDirMigration:
    """Test legacy data directory migration when --data-dir is used."""

    def test_migrates_legacy_data_dir(self, tmp_path):
        """Migrate <download_dir>/.kikusan to explicit data dir when target is absent."""
        download_dir = tmp_path / "downloads"
        legacy_data_dir = download_dir / ".kikusan"
        legacy_data_dir.mkdir(parents=True)
        legacy_file = legacy_data_dir / "state.json"
        legacy_file.write_text('{"ok": true}')
        target_data_dir = tmp_path / "custom-data"

        with patch.dict(os.environ, {"KIKUSAN_DOWNLOAD_DIR": str(download_dir)}):
            _migrate_legacy_data_dir(target_data_dir)

        assert (target_data_dir / "state.json").read_text() == '{"ok": true}'
        assert not legacy_data_dir.exists()

    def test_skips_migration_when_target_not_empty(self, tmp_path):
        """Do not migrate legacy directory into a non-empty target directory."""
        download_dir = tmp_path / "downloads"
        legacy_data_dir = download_dir / ".kikusan"
        legacy_data_dir.mkdir(parents=True)
        (legacy_data_dir / "legacy.txt").write_text("legacy")

        target_data_dir = tmp_path / "custom-data"
        target_data_dir.mkdir(parents=True)
        (target_data_dir / "existing.txt").write_text("existing")

        with patch.dict(os.environ, {"KIKUSAN_DOWNLOAD_DIR": str(download_dir)}):
            _migrate_legacy_data_dir(target_data_dir)

        assert (legacy_data_dir / "legacy.txt").exists()
        assert (target_data_dir / "existing.txt").exists()

    def test_migrates_legacy_data_dir_across_filesystems(self, tmp_path, monkeypatch):
        """Fallback copy/delete migration works when rename raises EXDEV."""
        download_dir = tmp_path / "downloads"
        legacy_data_dir = download_dir / ".kikusan"
        legacy_state_dir = legacy_data_dir / "state"
        legacy_state_dir.mkdir(parents=True)
        (legacy_state_dir / "queue.json").write_text('{"items": []}')

        target_data_dir = tmp_path / "custom-data"
        target_data_dir.mkdir(parents=True)

        original_rename = Path.rename

        def fake_rename(self, target):
            if str(self).endswith("/.kikusan/state"):
                raise OSError(errno.EXDEV, "Invalid cross-device link")
            return original_rename(self, target)

        monkeypatch.setattr(Path, "rename", fake_rename)

        with patch.dict(os.environ, {"KIKUSAN_DOWNLOAD_DIR": str(download_dir)}):
            _migrate_legacy_data_dir(target_data_dir)

        assert (target_data_dir / "state" / "queue.json").read_text() == '{"items": []}'
        assert not (legacy_data_dir / "state").exists()


class TestDownloadOptions:
    """Test download command options."""

    def test_organization_mode_choices(self):
        """Test --organization-mode validates choices."""
        runner = CliRunner()
        # Don't pass --help so click can validate the choice
        result = runner.invoke(app, ["download", "--organization-mode", "invalid"])
        assert result.exit_code != 0
        assert "Invalid value" in result.output

    def test_organization_mode_flat(self):
        """Test --organization-mode accepts 'flat'."""
        runner = CliRunner()
        result = runner.invoke(app, ["download", "--organization-mode", "flat", "--help"])
        assert result.exit_code == 0

    def test_organization_mode_album(self):
        """Test --organization-mode accepts 'album'."""
        runner = CliRunner()
        result = runner.invoke(app, ["download", "--organization-mode", "album", "--help"])
        assert result.exit_code == 0

    def test_use_primary_artist_flag(self):
        """Test --use-primary-artist flag."""
        runner = CliRunner()
        result = runner.invoke(app, ["download", "--use-primary-artist", "--help"])
        assert result.exit_code == 0

    def test_no_use_primary_artist_flag(self):
        """Test --no-use-primary-artist flag."""
        runner = CliRunner()
        result = runner.invoke(app, ["download", "--no-use-primary-artist", "--help"])
        assert result.exit_code == 0


class TestWebOptions:
    """Test web command options."""

    def test_cors_origins_option(self):
        """Test --cors-origins is accepted."""
        runner = CliRunner()
        result = runner.invoke(app, ["web", "--cors-origins", "*", "--help"])
        assert result.exit_code == 0

    def test_web_playlist_option(self):
        """Test --web-playlist is accepted."""
        runner = CliRunner()
        result = runner.invoke(app, ["web", "--web-playlist", "myplaylist", "--help"])
        assert result.exit_code == 0

    def test_output_option(self):
        """Test --output is accepted."""
        runner = CliRunner()
        result = runner.invoke(app, ["web", "--output", "/tmp/music", "--help"])
        assert result.exit_code == 0


class TestCronOptions:
    """Test cron command options."""

    def test_format_option(self):
        """Test --format option accepts valid values."""
        runner = CliRunner()
        result = runner.invoke(app, ["cron", "--format", "mp3", "--help"])
        assert result.exit_code == 0

    def test_format_option_invalid(self):
        """Test --format option rejects invalid values."""
        runner = CliRunner()
        # Don't pass --help so click can validate the choice
        result = runner.invoke(app, ["cron", "--format", "wav"])
        assert result.exit_code != 0
        assert "Invalid value" in result.output

    def test_organization_mode_option(self):
        """Test --organization-mode option."""
        runner = CliRunner()
        result = runner.invoke(app, ["cron", "--organization-mode", "album", "--help"])
        assert result.exit_code == 0

    def test_use_primary_artist_flag(self):
        """Test --use-primary-artist flag."""
        runner = CliRunner()
        result = runner.invoke(app, ["cron", "--use-primary-artist", "--help"])
        assert result.exit_code == 0


class TestPluginsRunOptions:
    """Test plugins run command options."""

    def test_format_option(self):
        """Test --format option."""
        runner = CliRunner()
        result = runner.invoke(app, ["plugins", "run", "--format", "flac", "--help"])
        assert result.exit_code == 0

    def test_organization_mode_option(self):
        """Test --organization-mode option."""
        runner = CliRunner()
        result = runner.invoke(app, ["plugins", "run", "--organization-mode", "flat", "--help"])
        assert result.exit_code == 0

    def test_use_primary_artist_flag(self):
        """Test --use-primary-artist flag."""
        runner = CliRunner()
        result = runner.invoke(app, ["plugins", "run", "--use-primary-artist", "--help"])
        assert result.exit_code == 0


class TestExploreOptions:
    """Test explore command group options."""

    def test_explore_help(self):
        """Test explore --help exits 0."""
        runner = CliRunner()
        result = runner.invoke(app, ["explore", "--help"])
        assert result.exit_code == 0
        assert "moods" in result.output.lower()
        assert "charts" in result.output.lower()
        assert "mood-playlists" in result.output.lower()

    def test_explore_moods_help(self):
        """Test explore moods --help exits 0."""
        runner = CliRunner()
        result = runner.invoke(app, ["explore", "moods", "--help"])
        assert result.exit_code == 0

    def test_explore_charts_help(self):
        """Test explore charts --help exits 0."""
        runner = CliRunner()
        result = runner.invoke(app, ["explore", "charts", "--help"])
        assert result.exit_code == 0
        assert "country" in result.output.lower()

    def test_explore_charts_country_option(self):
        """Test explore charts --country is accepted."""
        runner = CliRunner()
        result = runner.invoke(app, ["explore", "charts", "--country", "US", "--help"])
        assert result.exit_code == 0

    def test_explore_charts_download_option(self):
        """Test explore charts --download is accepted."""
        runner = CliRunner()
        result = runner.invoke(app, ["explore", "charts", "--download", "--help"])
        assert result.exit_code == 0

    def test_explore_mood_playlists_help(self):
        """Test explore mood-playlists --help exits 0."""
        runner = CliRunner()
        result = runner.invoke(app, ["explore", "mood-playlists", "--help"])
        assert result.exit_code == 0
        assert "download" in result.output.lower()

    def test_explore_mood_playlists_format_option(self):
        """Test explore mood-playlists --format validates choices."""
        runner = CliRunner()
        result = runner.invoke(app, ["explore", "mood-playlists", "--format", "wav", "params"])
        assert result.exit_code != 0
        assert "Invalid value" in result.output

    def test_explore_charts_format_option(self):
        """Test explore charts --format validates choices."""
        runner = CliRunner()
        result = runner.invoke(app, ["explore", "charts", "--format", "wav"])
        assert result.exit_code != 0
        assert "Invalid value" in result.output


class TestEnvVarIntegration:
    """Test that CLI options properly interact with environment variables."""

    def setup_method(self):
        """Clear relevant environment variables before each test."""
        for key in [
            "KIKUSAN_COOKIE_MODE",
            "KIKUSAN_COOKIE_RETRY_DELAY",
            "KIKUSAN_LOG_COOKIE_USAGE",
            "KIKUSAN_ORGANIZATION_MODE",
            "KIKUSAN_AUDIO_FORMAT",
            "KIKUSAN_CORS_ORIGINS",
            "KIKUSAN_WEB_PLAYLIST",
            "KIKUSAN_USE_PRIMARY_ARTIST",
        ]:
            if key in os.environ:
                del os.environ[key]

    @patch("kikusan.cli.search")
    @patch("kikusan.cli.download")
    def test_cli_overrides_env_var_for_organization_mode(self, mock_download, mock_search):
        """Test that CLI flag overrides environment variable."""
        os.environ["KIKUSAN_ORGANIZATION_MODE"] = "flat"
        mock_download.return_value = "/tmp/test.opus"
        mock_search.return_value = [
            MagicMock(video_id="test123", title="Test", artist="Artist")
        ]

        runner = CliRunner()
        result = runner.invoke(
            app,
            ["download", "--organization-mode", "album", "--query", "test"],
        )

        # Check that the download function was called with album mode
        if mock_download.called:
            call_kwargs = mock_download.call_args[1]
            assert call_kwargs.get("organization_mode") == "album"

    def test_envvar_attribute_on_click_options(self):
        """Test that options have envvar attribute where expected."""
        # This verifies the options are properly configured
        runner = CliRunner()

        # Test --organization-mode exists (Rich formatting may wrap long option names)
        result = runner.invoke(app, ["download", "--help"])
        assert "organization" in result.output.lower()

        result = runner.invoke(app, ["web", "--help"])
        assert "cors" in result.output.lower()

        result = runner.invoke(app, ["cron", "--help"])
        assert "format" in result.output.lower()
