from __future__ import annotations

import logging

import pytest

from src.persona.feature_flags import get_all_flags, is_enabled, log_startup_status


class MockPersonaFeatureFlagsConfig:
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


class MockPersonaConfig:
    def __init__(self, feature_flags=None):
        self.feature_flags = feature_flags or MockPersonaFeatureFlagsConfig(
            enable_persona_system=True,
            enable_style_protection=True,
            enable_identity_injection=True,
            enable_perception=True,
            enable_self_review=True,
            enable_adjustment=True,
            enable_autonomous_evolution=False,
            enable_inner_reaction=False,
            enable_hard_fact_guard=True,
        )


class MockSettings:
    def __init__(self, persona_config=None):
        self.persona = persona_config or MockPersonaConfig()


def _make_settings(**flag_overrides) -> MockSettings:
    defaults = dict(
        enable_persona_system=True,
        enable_style_protection=True,
        enable_identity_injection=True,
        enable_perception=True,
        enable_self_review=True,
        enable_adjustment=True,
        enable_autonomous_evolution=False,
        enable_inner_reaction=False,
        enable_hard_fact_guard=True,
    )
    defaults.update(flag_overrides)
    ff = MockPersonaFeatureFlagsConfig(**defaults)
    return MockSettings(MockPersonaConfig(feature_flags=ff))


class TestIsEnabled:
    def test_enabled_flag_returns_true(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("src.persona.feature_flags.get_settings", lambda: _make_settings(enable_perception=True))
        assert is_enabled("ENABLE_PERCEPTION") is True

    def test_disabled_flag_returns_false(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("src.persona.feature_flags.get_settings", lambda: _make_settings(enable_style_protection=False))
        assert is_enabled("ENABLE_STYLE_PROTECTION") is False

    def test_unknown_flag_returns_false(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("src.persona.feature_flags.get_settings", lambda: _make_settings())
        assert is_enabled("ENABLE_NONEXISTENT") is False

    def test_hard_fact_guard_disabled(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("src.persona.feature_flags.get_settings", lambda: _make_settings(enable_hard_fact_guard=False))
        assert is_enabled("ENABLE_HARD_FACT_GUARD") is False

    def test_persona_system_disabled_other_flags_return_false(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr("src.persona.feature_flags.get_settings", lambda: _make_settings(enable_persona_system=False))
        assert is_enabled("ENABLE_PERCEPTION") is False
        assert is_enabled("ENABLE_STYLE_PROTECTION") is False

    def test_persona_system_disabled_hard_fact_guard_still_works(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr("src.persona.feature_flags.get_settings", lambda: _make_settings(enable_persona_system=False, enable_hard_fact_guard=True))
        assert is_enabled("ENABLE_HARD_FACT_GUARD") is True


class TestGetAllFlags:
    def test_returns_all_flags(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("src.persona.feature_flags.get_settings", lambda: _make_settings())
        flags = get_all_flags()
        assert flags["ENABLE_PERSONA_SYSTEM"] is True
        assert flags["ENABLE_STYLE_PROTECTION"] is True
        assert flags["ENABLE_AUTONOMOUS_EVOLUTION"] is False
        assert flags["ENABLE_INNER_REACTION"] is False
        assert len(flags) == 9

    def test_flags_reflect_disabled_state(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("src.persona.feature_flags.get_settings", lambda: _make_settings(enable_perception=False, enable_self_review=False))
        flags = get_all_flags()
        assert flags["ENABLE_PERCEPTION"] is False
        assert flags["ENABLE_SELF_REVIEW"] is False
        assert flags["ENABLE_STYLE_PROTECTION"] is True


class TestLogStartupStatus:
    def test_logs_flag_status(self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
        monkeypatch.setattr("src.persona.feature_flags.get_settings", lambda: _make_settings())
        caplog.set_level(logging.INFO)
        log_startup_status()
        assert "[persona] feature flags:" in caplog.text
        assert "ENABLE_PERSONA_SYSTEM=ON" in caplog.text
        assert "ENABLE_AUTONOMOUS_EVOLUTION=OFF" in caplog.text

    def test_logs_correctly_when_all_off(self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
        monkeypatch.setattr("src.persona.feature_flags.get_settings", lambda: _make_settings(
            enable_persona_system=True,
            enable_hard_fact_guard=False,
            enable_style_protection=False,
            enable_identity_injection=False,
            enable_perception=False,
            enable_self_review=False,
            enable_adjustment=False,
            enable_autonomous_evolution=False,
            enable_inner_reaction=False,
        ))
        caplog.set_level(logging.INFO)
        log_startup_status()
        assert "ENABLE_PERSONA_SYSTEM=ON" in caplog.text
        assert caplog.text.count("=OFF") == 8