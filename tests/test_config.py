from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from pydantic import ValidationError

from src.config import (
    EvolutionConfig,
    PersonaCompilerConfig,
    PersonaConfig,
    PersonaStyleConfig,
    Settings,
    _load_yaml,
    _resolve_env_vars,
    get_settings,
    reload_settings,
)


class TestResolveEnvVars:
    def test_resolve_simple_string_with_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TEST_VAR", "resolved_value")
        result = _resolve_env_vars("prefix_${TEST_VAR}_suffix")
        assert result == "prefix_resolved_value_suffix"

    def test_resolve_missing_env_var_becomes_empty(self) -> None:
        result = _resolve_env_vars("${NONEXISTENT_VAR}")
        assert result == ""

    def test_resolve_nested_dict(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("KEY", "secret")
        data = {"api_key": "${KEY}", "nested": {"deep": "${KEY}"}}
        result = _resolve_env_vars(data)
        assert result["api_key"] == "secret"
        assert result["nested"]["deep"] == "secret"

    def test_resolve_list(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("A", "1")
        monkeypatch.setenv("B", "2")
        result = _resolve_env_vars(["${A}", "${B}"])
        assert result == ["1", "2"]

    def test_passthrough_non_string(self) -> None:
        result = _resolve_env_vars(42)
        assert result == 42


class TestLoadYaml:
    def test_load_valid_yaml(self) -> None:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False, encoding="utf-8"
        ) as f:
            f.write("agent:\n  name: TestAgent\n  mode: persona\n")
            tmp_path = f.name

        try:
            data = _load_yaml(tmp_path)
            assert data["agent"]["name"] == "TestAgent"
            assert data["agent"]["mode"] == "persona"
        finally:
            Path(tmp_path).unlink()

    def test_load_nonexistent_file_returns_empty(self) -> None:
        data = _load_yaml("/nonexistent/path/config.yaml")
        assert data == {}

    def test_load_empty_file_returns_empty(self) -> None:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False, encoding="utf-8"
        ) as f:
            tmp_path = f.name

        try:
            data = _load_yaml(tmp_path)
            assert data == {}
        finally:
            Path(tmp_path).unlink()

    def test_load_with_env_var_substitution(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MY_KEY", "my-secret")
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False, encoding="utf-8"
        ) as f:
            f.write("models:\n  providers:\n    test:\n      api_key: ${MY_KEY}\n")
            tmp_path = f.name

        try:
            data = _load_yaml(tmp_path)
            assert data["models"]["providers"]["test"]["api_key"] == "my-secret"
        finally:
            Path(tmp_path).unlink()


class TestPersonaConfig:
    def test_default_values(self) -> None:
        config = PersonaConfig()
        assert config.style.drift_threshold == 0.25
        assert config.style.review_drift_threshold == 0.15
        assert config.style.enable_proactive is False
        assert config.style.style_dimensions == 7
        assert config.style.anchor_dimensions == 128
        assert config.style.decision_anchor_dimensions == 256
        assert config.compiler.min_input_chars == 100
        assert config.compiler.max_input_chars == 1000000
        assert config.compiler.language_samples_min == 500
        assert config.compiler.language_samples_max == 1000

    def test_drift_threshold_locked(self) -> None:
        from src.config import PersonaStyleConfig
        with pytest.raises(ValidationError):
            PersonaConfig(style=PersonaStyleConfig(drift_threshold=0.99))

    def test_review_drift_threshold_locked(self) -> None:
        from src.config import PersonaStyleConfig
        with pytest.raises(ValidationError):
            PersonaConfig(style=PersonaStyleConfig(review_drift_threshold=0.99))

    def test_enable_proactive_locked(self) -> None:
        from src.config import PersonaStyleConfig
        with pytest.raises(ValidationError):
            PersonaConfig(style=PersonaStyleConfig(enable_proactive=True))

    def test_anchor_dimensions_locked(self) -> None:
        from src.config import PersonaStyleConfig
        with pytest.raises(ValidationError):
            PersonaConfig(style=PersonaStyleConfig(anchor_dimensions=256))

    def test_decision_anchor_dimensions_locked(self) -> None:
        from src.config import PersonaStyleConfig
        with pytest.raises(ValidationError):
            PersonaConfig(style=PersonaStyleConfig(decision_anchor_dimensions=128))

    def test_min_input_chars_locked(self) -> None:
        from src.config import PersonaCompilerConfig
        with pytest.raises(ValidationError):
            PersonaConfig(compiler=PersonaCompilerConfig(min_input_chars=50))

    def test_max_input_chars_locked(self) -> None:
        from src.config import PersonaCompilerConfig
        with pytest.raises(ValidationError):
            PersonaConfig(compiler=PersonaCompilerConfig(max_input_chars=500))

    def test_language_samples_min_locked(self) -> None:
        from src.config import PersonaCompilerConfig
        with pytest.raises(ValidationError):
            PersonaConfig(compiler=PersonaCompilerConfig(language_samples_min=100))

    def test_language_samples_max_locked(self) -> None:
        from src.config import PersonaCompilerConfig
        with pytest.raises(ValidationError):
            PersonaConfig(compiler=PersonaCompilerConfig(language_samples_max=2000))

    def test_valid_locked_values_accepted(self) -> None:
        config = PersonaConfig(
            style=PersonaStyleConfig(
                drift_threshold=0.25,
                review_drift_threshold=0.15,
                enable_proactive=False,
                style_dimensions=7,
                anchor_dimensions=128,
                decision_anchor_dimensions=256,
            ),
            compiler=PersonaCompilerConfig(
                min_input_chars=100,
                max_input_chars=1000000,
                language_samples_min=500,
                language_samples_max=1000,
            ),
        )
        assert config.style.drift_threshold == 0.25


class TestEvolutionConfig:
    def test_default_values(self) -> None:
        config = EvolutionConfig()
        assert config.birth_threshold == 40
        assert config.birth_window_days == 7
        assert config.fusion_threshold == 3

    def test_birth_threshold_locked(self) -> None:
        with pytest.raises(ValidationError):
            EvolutionConfig(birth_threshold=50)


class TestEmbeddingConfig:
    def test_dedup_threshold_locked(self) -> None:
        from src.config import EmbeddingConfig

        with pytest.raises(ValidationError):
            EmbeddingConfig(dedup_threshold=0.5)


class TestSettings:
    def test_default_settings(self) -> None:
        settings = Settings()
        assert settings.agent.name == "ShuyuanCore"
        assert settings.agent.mode == "general"
        assert settings.deploy.port == 8005
        assert settings.deploy.host == "0.0.0.0"

    def test_extra_field_forbidden(self) -> None:
        with pytest.raises(ValidationError):
            Settings(unknown_field=123)  # type: ignore[call-arg]

    def test_env_var_override_top_level(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("AGENT__NAME", "EnvAgent")
        settings = Settings()
        assert settings.agent.name == "EnvAgent"

    def test_deploy_config_defaults(self) -> None:
        settings = Settings()
        assert settings.deploy.log_level == "info"
        assert settings.deploy.workers == 1
        assert len(settings.deploy.methods) == 6


class TestGetSettings:
    def test_singleton_returns_same_instance(self) -> None:
        s1 = get_settings()
        s2 = get_settings()
        assert s1 is s2

    def test_reload_returns_new_instance(self) -> None:
        s1 = get_settings()
        s2 = reload_settings()
        assert s1 is not s2

    def test_get_settings_with_custom_yaml(self) -> None:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False, encoding="utf-8"
        ) as f:
            f.write("agent:\n  name: CustomAgent\n")
            tmp_path = f.name

        try:
            s = reload_settings((tmp_path,))
            assert s.agent.name == "CustomAgent"
        finally:
            Path(tmp_path).unlink()


class TestSettingsModelConfig:
    def test_env_nested_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DEPLOY__PORT", "9999")
        settings = Settings()
        assert settings.deploy.port == 9999
