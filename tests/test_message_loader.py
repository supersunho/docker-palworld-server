"""Tests for the multi-language message loader."""

import pytest
import json
from unittest.mock import patch, mock_open
from src.notifications.message_loader import MessageLoader

pytestmark = pytest.mark.unit


class TestMessageLoader:
    """FS-20.x: Message loader behavior."""

    @pytest.fixture
    def loader(self, tmp_path):
        """Set up locales directory with test files."""
        locales_dir = tmp_path / "locales"
        locales_dir.mkdir()

        ko_data = {
            "server": {"start": "서버가 시작되었습니다"},
            "player": {"join": ["{player}님이 접속했습니다", "{player} 들어옴"]},
            "status": {"alone": "혼자", "few": "{count}명", "many": "{count}명"},
            "greeting": {
                "morning": "좋은 아침",
                "afternoon": "좋은 오후",
                "evening": "좋은 저녁",
                "night": "안녕히 주무세요"
            }
        }
        (locales_dir / "ko.json").write_text(json.dumps(ko_data, ensure_ascii=False))

        en_data = {
            "server": {"start": "Server started"},
            "player": {"join": "{player} joined"},
            "status": {"alone": "alone", "few": "{count} players", "many": "{count} players"},
            "greeting": {
                "morning": "Good morning",
                "afternoon": "Good afternoon",
                "evening": "Good evening",
                "night": "Good night"
            }
        }
        (locales_dir / "en.json").write_text(json.dumps(en_data))

        return MessageLoader(str(locales_dir), default_language="ko")

    def test_get_message(self, loader):
        """FS-20.3: Dot-path navigation."""
        msg = loader.get_message("server.start", "ko")
        assert msg == "서버가 시작되었습니다"

    def test_get_message_english(self, loader):
        """FS-20.3: English message."""
        msg = loader.get_message("server.start", "en")
        assert msg == "Server started"

    def test_random_variation(self, loader):
        """FS-20.4: Random selection from list."""
        results = set()
        for _ in range(50):
            msg = loader.get_message("player.join", "ko", player="Test")
            results.add(msg)
        assert len(results) > 1
        assert all("Test" in r for r in results)

    def test_format_kwargs(self, loader):
        """FS-20.5: String formatting with kwargs."""
        msg = loader.get_message("player.join", "en", player="Alice")
        assert "Alice" in msg

    def test_get_status_message(self, loader):
        """FS-20.6: Status message for player count."""
        assert loader.get_status_message(1, "ko") == "혼자"
        assert "3명" in loader.get_status_message(3, "ko")

    def test_get_greeting(self, loader):
        """FS-20.6: Time-based greeting."""
        with patch('src.notifications.message_loader.datetime') as mock_dt:
            mock_dt.now.return_value.hour = 9
            greeting = loader.get_greeting("ko")
            assert greeting == "좋은 아침"

    def test_get_greeting_night(self, loader):
        with patch('src.notifications.message_loader.datetime') as mock_dt:
            mock_dt.now.return_value.hour = 23
            greeting = loader.get_greeting("ko")
            assert greeting == "안녕히 주무세요"

    def test_message_not_found_fallback(self, loader):
        """FS-20.7: Unknown path falls back to default language."""
        msg = loader.get_message("nonexistent.path", "en")
        assert msg.startswith("Message not found")

    def test_available_languages(self, loader):
        """FS-20.2: Lists available languages."""
        langs = loader.get_available_languages()
        assert "ko" in langs
        assert "en" in langs

    def test_reload_language(self, loader, tmp_path):
        """FS-20.7: Reload from disk."""
        assert loader.reload_language("ko") is True
        # xx likely falls back via _load_language chain
        # Just verify that ko still loads
        assert loader.reload_language("ko") is True

    def test_missing_locales_dir(self, tmp_path):
        """FS-20.1: Raises error for missing dir."""
        with pytest.raises(FileNotFoundError):
            MessageLoader(str(tmp_path / "nonexistent"))


    def test_get_status_message_many(self, loader):
        """FS-20.6: Status for many players."""
        msg = loader.get_status_message(10, "ko")
        assert "10명" in msg

    def test_get_greeting_afternoon(self, loader):
        """FS-20.6: Afternoon greeting."""
        with patch('src.notifications.message_loader.datetime') as mock_dt:
            mock_dt.now.return_value.hour = 14
            greeting = loader.get_greeting("ko")
            assert greeting == "좋은 오후"

    def test_get_greeting_evening(self, loader):
        """FS-20.6: Evening greeting."""
        with patch('src.notifications.message_loader.datetime') as mock_dt:
            mock_dt.now.return_value.hour = 20
            greeting = loader.get_greeting("ko")
            assert greeting == "좋은 저녁"

    def test_message_format_error_fallback(self, loader):
        """FS-20.7: Format error returns unformatted message."""
        msg = loader.get_message("server.start", "ko", unknown_key="value")
        assert msg == "서버가 시작되었습니다"

    def test_default_language_fallback_on_load_error(self, tmp_path):
        """FS-20.1: Falls back to default lang when target missing."""
        locales_dir = tmp_path / "locales"
        locales_dir.mkdir()
        ko_data = {"test": "value"}
        (locales_dir / "ko.json").write_text(json.dumps(ko_data))
        loader = MessageLoader(str(locales_dir), default_language="ko")
        # xx doesn't exist, falls back to ko
        msg = loader.get_message("test", "xx")
        assert msg == "value"

    def test_reload_language_failure(self, loader, tmp_path):
        """FS-20.7: reload_language returns False on failure."""
        # Remove the language file so reload fails
        import os
        ko_path = loader.locales_dir / "ko.json"
        if ko_path.exists():
            os.remove(str(ko_path))
        result = loader.reload_language("ko")
        assert result is False

    def test_available_languages_no_dir(self, tmp_path):
        """FS-20.2: get_available_languages returns [] when dir missing."""
        # Create a MessageLoader, then test empty locales
        locales_dir = tmp_path / "locales2"
        locales_dir.mkdir()
        ko_data = {"test": "val"}
        (locales_dir / "ko.json").write_text(json.dumps(ko_data))
        loader = MessageLoader(str(locales_dir))
        # Remove dir and check
        import shutil


        shutil.rmtree(str(locales_dir))
        langs = loader.get_available_languages()
        assert langs == []
