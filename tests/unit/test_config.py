"""Tests for configuration."""

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from shesha.config import SheshaConfig


def test_config_defaults():
    """Config has sensible defaults."""
    config = SheshaConfig()
    assert config.model == "claude-sonnet-4-20250514"
    assert config.pool_size == 3
    assert config.max_iterations == 20


def test_config_from_kwargs():
    """Config accepts keyword arguments."""
    config = SheshaConfig(model="gpt-4", pool_size=5)
    assert config.model == "gpt-4"
    assert config.pool_size == 5


def test_config_from_env():
    """Config reads from environment variables."""
    with patch.dict(os.environ, {"SHESHA_MODEL": "test-model"}):
        config = SheshaConfig.from_env()
        assert config.model == "test-model"


def test_config_from_yaml_file(tmp_path: Path):
    """Config reads from YAML file."""
    config_file = tmp_path / "shesha.yaml"
    config_file.write_text("model: yaml-model\npool_size: 7\n")
    config = SheshaConfig.from_file(config_file)
    assert config.model == "yaml-model"
    assert config.pool_size == 7


def test_config_from_json_file(tmp_path: Path):
    """Config reads from JSON file."""
    config_file = tmp_path / "shesha.json"
    config_file.write_text('{"model": "json-model", "max_iterations": 10}')
    config = SheshaConfig.from_file(config_file)
    assert config.model == "json-model"
    assert config.max_iterations == 10


def test_config_hierarchy(tmp_path: Path):
    """Config follows hierarchy: defaults < file < env < kwargs."""
    config_file = tmp_path / "shesha.yaml"
    config_file.write_text("model: file-model\npool_size: 5\n")
    with patch.dict(os.environ, {"SHESHA_MODEL": "env-model"}):
        config = SheshaConfig.load(
            config_path=config_file,
            model="kwarg-model",  # Highest priority
        )
        assert config.model == "kwarg-model"  # kwarg wins
        assert config.pool_size == 5  # from file


class TestMaxTracesConfig:
    """Tests for max_traces_per_project config."""

    def test_default_max_traces_is_50(self) -> None:
        """Default max_traces_per_project is 50."""
        config = SheshaConfig()
        assert config.max_traces_per_project == 50

    def test_max_traces_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """SHESHA_MAX_TRACES_PER_PROJECT env var sets max_traces_per_project."""
        monkeypatch.setenv("SHESHA_MAX_TRACES_PER_PROJECT", "100")
        config = SheshaConfig.load()
        assert config.max_traces_per_project == 100


class TestVerifyCitationsConfig:
    """Tests for verify_citations config."""

    def test_default_verify_citations_is_true(self) -> None:
        """Default verify_citations is True."""
        config = SheshaConfig()
        assert config.verify_citations is True

    def test_verify_citations_from_env_false(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """SHESHA_VERIFY_CITATIONS=false disables verification."""
        monkeypatch.setenv("SHESHA_VERIFY_CITATIONS", "false")
        config = SheshaConfig.load()
        assert config.verify_citations is False

    def test_verify_citations_from_env_true(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """SHESHA_VERIFY_CITATIONS=true enables verification."""
        monkeypatch.setenv("SHESHA_VERIFY_CITATIONS", "true")
        config = SheshaConfig.load()
        assert config.verify_citations is True

    def test_verify_citations_from_file(self, tmp_path: Path) -> None:
        """verify_citations can be set from config file."""
        config_file = tmp_path / "shesha.yaml"
        config_file.write_text("verify_citations: false\n")
        config = SheshaConfig.from_file(config_file)
        assert config.verify_citations is False

    def test_verify_citations_override(self) -> None:
        """verify_citations can be overridden via kwargs."""
        config = SheshaConfig.load(verify_citations=False)
        assert config.verify_citations is False

    def test_verify_citations_from_env_method(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """from_env() respects SHESHA_VERIFY_CITATIONS."""
        monkeypatch.setenv("SHESHA_VERIFY_CITATIONS", "false")
        config = SheshaConfig.from_env()
        assert config.verify_citations is False

    def test_verify_citations_invalid_env_raises_in_load(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """load() raises ValueError for unrecognized SHESHA_VERIFY_CITATIONS value."""
        monkeypatch.setenv("SHESHA_VERIFY_CITATIONS", "treu")
        with pytest.raises(ValueError, match="SHESHA_VERIFY_CITATIONS"):
            SheshaConfig.load()

    def test_verify_citations_invalid_env_raises_in_from_env(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """from_env() raises ValueError for unrecognized SHESHA_VERIFY_CITATIONS value."""
        monkeypatch.setenv("SHESHA_VERIFY_CITATIONS", "yse")
        with pytest.raises(ValueError, match="SHESHA_VERIFY_CITATIONS"):
            SheshaConfig.from_env()


class TestVerifyConfig:
    """Tests for verify config field."""

    def test_verify_defaults_false(self) -> None:
        """verify defaults to False."""
        config = SheshaConfig()
        assert config.verify is False

    def test_verify_can_be_set_true(self) -> None:
        """verify can be set to True."""
        config = SheshaConfig(verify=True)
        assert config.verify is True


def test_config_has_no_allowed_hosts():
    """allowed_hosts was removed — config must not have it."""
    config = SheshaConfig()
    assert not hasattr(config, "allowed_hosts")


class TestMissingEnvMappings:
    """All config fields should be settable via environment variables."""

    def test_keep_raw_files_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SHESHA_KEEP_RAW_FILES", "false")
        config = SheshaConfig.load()
        assert config.keep_raw_files is False

    def test_container_memory_mb_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SHESHA_CONTAINER_MEMORY_MB", "1024")
        config = SheshaConfig.load()
        assert config.container_memory_mb == 1024

    def test_execution_timeout_sec_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SHESHA_EXECUTION_TIMEOUT_SEC", "60")
        config = SheshaConfig.load()
        assert config.execution_timeout_sec == 60

    def test_sandbox_image_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SHESHA_SANDBOX_IMAGE", "custom-sandbox:latest")
        config = SheshaConfig.load()
        assert config.sandbox_image == "custom-sandbox:latest"

    def test_max_output_chars_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SHESHA_MAX_OUTPUT_CHARS", "50000")
        config = SheshaConfig.load()
        assert config.max_output_chars == 50000

    def test_verify_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SHESHA_VERIFY", "true")
        config = SheshaConfig.load()
        assert config.verify is True
