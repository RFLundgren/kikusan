"""Tests for playlist URL validation in cron config."""

from kikusan.cron.config import validate_url


def test_validate_url_accepts_deezer_playlist_url():
    validate_url("https://www.deezer.com/playlist/908622995", "deezer-list")


def test_validate_url_accepts_localized_deezer_playlist_url():
    validate_url("https://www.deezer.com/us/playlist/908622995", "deezer-list")
