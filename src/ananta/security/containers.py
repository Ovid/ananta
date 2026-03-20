"""Container security configuration."""

from dataclasses import dataclass
from typing import Any


@dataclass
class ContainerSecurityConfig:
    """Security configuration for sandbox containers."""

    cap_drop: list[str] | None = None
    privileged: bool = False
    network_disabled: bool = True
    read_only: bool = True
    security_opt: list[str] | None = None
    tmpfs: dict[str, str] | None = None

    def __post_init__(self) -> None:
        """Set defaults after initialization."""
        if self.cap_drop is None:
            self.cap_drop = ["ALL"]
        if self.security_opt is None:
            self.security_opt = ["no-new-privileges:true"]
        if self.tmpfs is None:
            self.tmpfs = {"/tmp": "size=64m,noexec,nosuid,nodev"}

    def to_docker_kwargs(self) -> dict[str, Any]:
        """Convert to kwargs for docker-py containers.run()."""
        kwargs: dict[str, Any] = {
            "cap_drop": self.cap_drop,
            "privileged": self.privileged,
            "network_disabled": self.network_disabled,
            "read_only": self.read_only,
            "security_opt": self.security_opt,
        }
        if self.tmpfs:
            kwargs["tmpfs"] = self.tmpfs
        return kwargs


# Default secure configuration
DEFAULT_SECURITY = ContainerSecurityConfig()
