"""Tests for container security configuration."""

from ananta.security.containers import DEFAULT_SECURITY, ContainerSecurityConfig


class TestContainerSecurityConfig:
    """Tests for ContainerSecurityConfig."""

    def test_default_drops_all_capabilities(self) -> None:
        """Default config drops all capabilities."""
        config = ContainerSecurityConfig()
        assert config.cap_drop == ["ALL"]

    def test_default_not_privileged(self) -> None:
        """Default config is not privileged."""
        config = ContainerSecurityConfig()
        assert config.privileged is False

    def test_default_network_disabled(self) -> None:
        """Default config has network disabled."""
        config = ContainerSecurityConfig()
        assert config.network_disabled is True

    def test_default_read_only(self) -> None:
        """Default config has read-only root filesystem."""
        config = ContainerSecurityConfig()
        assert config.read_only is True

    def test_default_no_new_privileges(self) -> None:
        """Default config prevents gaining new privileges."""
        config = ContainerSecurityConfig()
        assert "no-new-privileges:true" in config.security_opt

    def test_to_docker_kwargs(self) -> None:
        """Converts to docker-py kwargs correctly."""
        config = ContainerSecurityConfig()
        kwargs = config.to_docker_kwargs()
        assert kwargs["cap_drop"] == ["ALL"]
        assert kwargs["privileged"] is False
        assert kwargs["network_disabled"] is True
        assert kwargs["read_only"] is True
        assert "no-new-privileges:true" in kwargs["security_opt"]

    def test_custom_config(self) -> None:
        """Custom configuration overrides defaults."""
        config = ContainerSecurityConfig(
            cap_drop=["NET_ADMIN"],
            network_disabled=False,
        )
        assert config.cap_drop == ["NET_ADMIN"]
        assert config.network_disabled is False

    def test_default_tmpfs(self) -> None:
        """Default config has tmpfs mount for /tmp with restrictions."""
        config = ContainerSecurityConfig()
        assert config.tmpfs is not None
        assert "/tmp" in config.tmpfs
        assert "noexec" in config.tmpfs["/tmp"]
        assert "nosuid" in config.tmpfs["/tmp"]
        assert "nodev" in config.tmpfs["/tmp"]
        assert "size=64m" in config.tmpfs["/tmp"]

    def test_custom_tmpfs_override(self) -> None:
        """Custom tmpfs overrides default."""
        config = ContainerSecurityConfig(tmpfs={"/tmp": "size=128m"})
        assert config.tmpfs == {"/tmp": "size=128m"}

    def test_tmpfs_empty_dict_disables(self) -> None:
        """Passing empty dict disables tmpfs."""
        config = ContainerSecurityConfig(tmpfs={})
        assert config.tmpfs == {}

    def test_to_docker_kwargs_includes_tmpfs(self) -> None:
        """to_docker_kwargs includes tmpfs in output."""
        config = ContainerSecurityConfig()
        kwargs = config.to_docker_kwargs()
        assert "tmpfs" in kwargs
        assert "/tmp" in kwargs["tmpfs"]

    def test_default_security_singleton(self) -> None:
        """DEFAULT_SECURITY is a pre-configured instance."""
        assert DEFAULT_SECURITY.cap_drop == ["ALL"]
        assert DEFAULT_SECURITY.privileged is False
