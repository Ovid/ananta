"""Configuration for Ananta."""

import json
import os
from dataclasses import dataclass, fields
from pathlib import Path
from typing import Any

import yaml

_BOOL_TRUE = {"true", "1", "yes"}
_BOOL_FALSE = {"false", "0", "no"}


def _parse_bool_env(env_var: str, value: str) -> bool:
    """Parse a boolean environment variable, raising on unrecognized values."""
    lower = value.lower()
    if lower in _BOOL_TRUE:
        return True
    if lower in _BOOL_FALSE:
        return False
    raise ValueError(
        f"Invalid value for {env_var}: {value!r}. "
        f"Expected one of: {', '.join(sorted(_BOOL_TRUE | _BOOL_FALSE))}"
    )


@dataclass
class AnantaConfig:
    """Configuration for Ananta."""

    # LLM settings
    model: str = "claude-sonnet-4-20250514"
    api_key: str | None = None

    # Storage
    storage_path: str = "./ananta_data"
    keep_raw_files: bool = True

    # Sandbox
    pool_size: int = 3
    container_memory_mb: int = 512
    execution_timeout_sec: int = 30
    sandbox_image: str = "ananta-sandbox"

    # RLM behavior
    max_iterations: int = 20
    max_output_chars: int = 20_000

    # Verification
    verify_citations: bool = True

    # Semantic verification
    verify: bool = False

    # Trace logging
    max_traces_per_project: int = 50

    @classmethod
    def from_env(cls) -> "AnantaConfig":
        """Create config from environment variables."""
        verify_env = os.environ.get("ANANTA_VERIFY_CITATIONS")
        verify = (
            _parse_bool_env("ANANTA_VERIFY_CITATIONS", verify_env)
            if verify_env is not None
            else cls.verify_citations
        )
        return cls(
            model=os.environ.get("ANANTA_MODEL", cls.model),
            api_key=os.environ.get("ANANTA_API_KEY"),
            storage_path=os.environ.get("ANANTA_STORAGE_PATH", cls.storage_path),
            pool_size=int(os.environ.get("ANANTA_POOL_SIZE", str(cls.pool_size))),
            max_iterations=int(os.environ.get("ANANTA_MAX_ITERATIONS", str(cls.max_iterations))),
            verify_citations=verify,
        )

    @classmethod
    def from_file(cls, path: Path | str) -> "AnantaConfig":
        """Create config from a YAML or JSON file."""
        path = Path(path)
        content = path.read_text()
        if path.suffix in {".yaml", ".yml"}:
            data = yaml.safe_load(content) or {}
        else:
            data = json.loads(content)
        # Filter to only valid fields
        valid_fields = {f.name for f in fields(cls)}
        filtered = {k: v for k, v in data.items() if k in valid_fields}
        return cls(**filtered)

    @classmethod
    def load(
        cls,
        config_path: Path | str | None = None,
        **overrides: Any,
    ) -> "AnantaConfig":
        """Load config with full hierarchy: defaults < file < env < kwargs."""
        # Start with defaults
        config_dict: dict[str, Any] = {}

        # Layer 2: File config
        if config_path:
            file_config = cls.from_file(config_path)
            for f in fields(cls):
                val = getattr(file_config, f.name)
                if val != f.default:
                    config_dict[f.name] = val

        # Layer 3: Environment variables
        env_map = {
            "ANANTA_MODEL": "model",
            "ANANTA_API_KEY": "api_key",
            "ANANTA_STORAGE_PATH": "storage_path",
            "ANANTA_KEEP_RAW_FILES": "keep_raw_files",
            "ANANTA_POOL_SIZE": "pool_size",
            "ANANTA_CONTAINER_MEMORY_MB": "container_memory_mb",
            "ANANTA_EXECUTION_TIMEOUT_SEC": "execution_timeout_sec",
            "ANANTA_SANDBOX_IMAGE": "sandbox_image",
            "ANANTA_MAX_ITERATIONS": "max_iterations",
            "ANANTA_MAX_OUTPUT_CHARS": "max_output_chars",
            "ANANTA_VERIFY_CITATIONS": "verify_citations",
            "ANANTA_VERIFY": "verify",
            "ANANTA_MAX_TRACES_PER_PROJECT": "max_traces_per_project",
        }
        _int_fields = {
            "pool_size",
            "container_memory_mb",
            "execution_timeout_sec",
            "max_iterations",
            "max_output_chars",
            "max_traces_per_project",
        }
        _bool_fields = {"keep_raw_files", "verify_citations", "verify"}
        for env_var, field_name in env_map.items():
            if env_var in os.environ:
                env_val: Any = os.environ[env_var]
                if field_name in _int_fields:
                    env_val = int(env_val)
                elif field_name in _bool_fields:
                    env_val = _parse_bool_env(env_var, env_val)
                config_dict[field_name] = env_val

        # Layer 4: Explicit overrides (highest priority)
        for k, v in overrides.items():
            if v is not None:
                config_dict[k] = v

        return cls(**config_dict)
