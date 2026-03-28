from __future__ import annotations

from app import TwitchXApp


class TestSanitizeUsername:
    def test_plain(self) -> None:
        assert TwitchXApp._sanitize_username("xqc") == "xqc"

    def test_full_url(self) -> None:
        assert TwitchXApp._sanitize_username("https://www.twitch.tv/xqc") == "xqc"

    def test_no_scheme(self) -> None:
        assert TwitchXApp._sanitize_username("twitch.tv/xqc") == "xqc"

    def test_whitespace(self) -> None:
        assert TwitchXApp._sanitize_username("  xqc  ") == "xqc"

    def test_invalid_chars(self) -> None:
        assert TwitchXApp._sanitize_username("xq!c") == "xqc"

    def test_empty(self) -> None:
        assert TwitchXApp._sanitize_username("") == ""

    def test_lowercases(self) -> None:
        assert TwitchXApp._sanitize_username("XqC") == "xqc"

    def test_url_with_path(self) -> None:
        assert TwitchXApp._sanitize_username("https://twitch.tv/just_ns") == "just_ns"

    def test_only_special_chars(self) -> None:
        assert TwitchXApp._sanitize_username("@#$%") == ""


class TestMigrateFavorites:
    def test_cleans_v1_urls(self, tmp_path, monkeypatch) -> None:
        """v1 string favorites are converted to v2 dict objects."""
        config = {
            "platforms": {"twitch": {}, "kick": {}, "youtube": {}},
            "favorites": ["https://twitch.tv/xqc", "just_ns", "twitch.tv/xqc", "good123"],
            "settings": {},
        }
        monkeypatch.setattr("app.load_config", lambda: config)
        saved = {}
        monkeypatch.setattr("app.save_config", lambda c: saved.update(c))

        app = TwitchXApp.__new__(TwitchXApp)
        app._api = type("FakeApi", (), {"set_window": lambda s, w: None})()  # type: ignore[assignment]
        app._config = config
        app._migrate_favorites()

        assert config["favorites"] == [
            {"platform": "twitch", "login": "xqc", "display_name": "xqc"},
            {"platform": "twitch", "login": "just_ns", "display_name": "just_ns"},
            {"platform": "twitch", "login": "good123", "display_name": "good123"},
        ]

    def test_noop_clean_v2(self, tmp_path, monkeypatch) -> None:
        """Clean v2 favorites are not re-saved."""
        config = {
            "platforms": {"twitch": {}, "kick": {}, "youtube": {}},
            "favorites": [
                {"platform": "twitch", "login": "xqc", "display_name": "xQc"},
                {"platform": "kick", "login": "trainwreck", "display_name": "Trainwreck"},
            ],
            "settings": {},
        }
        monkeypatch.setattr("app.load_config", lambda: config)
        save_called = []
        monkeypatch.setattr("app.save_config", lambda c: save_called.append(True))

        app = TwitchXApp.__new__(TwitchXApp)
        app._api = type("FakeApi", (), {"set_window": lambda s, w: None})()  # type: ignore[assignment]
        app._config = config
        app._migrate_favorites()

        assert save_called == []  # No save needed — already clean

    def test_deduplicates_v2(self, tmp_path, monkeypatch) -> None:
        """Duplicate v2 favorites are removed."""
        config = {
            "platforms": {"twitch": {}, "kick": {}, "youtube": {}},
            "favorites": [
                {"platform": "twitch", "login": "xqc", "display_name": "xQc"},
                {"platform": "twitch", "login": "xqc", "display_name": "xQc"},
            ],
            "settings": {},
        }
        monkeypatch.setattr("app.load_config", lambda: config)
        monkeypatch.setattr("app.save_config", lambda c: None)

        app = TwitchXApp.__new__(TwitchXApp)
        app._api = type("FakeApi", (), {"set_window": lambda s, w: None})()  # type: ignore[assignment]
        app._config = config
        app._migrate_favorites()

        assert len(config["favorites"]) == 1

    def test_same_login_different_platforms_kept(self, tmp_path, monkeypatch) -> None:
        """Same login on different platforms are NOT deduplicated."""
        config = {
            "platforms": {"twitch": {}, "kick": {}, "youtube": {}},
            "favorites": [
                {"platform": "twitch", "login": "xqc", "display_name": "xQc"},
                {"platform": "kick", "login": "xqc", "display_name": "xQc"},
            ],
            "settings": {},
        }
        monkeypatch.setattr("app.load_config", lambda: config)
        save_called = []
        monkeypatch.setattr("app.save_config", lambda c: save_called.append(True))

        app = TwitchXApp.__new__(TwitchXApp)
        app._api = type("FakeApi", (), {"set_window": lambda s, w: None})()  # type: ignore[assignment]
        app._config = config
        app._migrate_favorites()

        assert len(config["favorites"]) == 2
        assert save_called == []  # No change needed
