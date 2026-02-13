"""Tests for config module."""

from pathlib import Path


from nix_devbox.config import (
    CONFIG_FILE_NAMES,
    DEFAULT_LOG_DRIVER,
    DevboxConfig,
    LoggingConfig,
    ResourcesConfig,
    RunConfig,
    SecurityConfig,
    _parse_logging_config,
    _parse_resources_config,
    _parse_run_config,
    _parse_security_config,
    find_config,
)


class TestConstants:
    """Tests for module constants."""

    def test_config_file_names(self):
        assert "devbox.yaml" in CONFIG_FILE_NAMES
        assert ".devbox.yaml" in CONFIG_FILE_NAMES
        assert CONFIG_FILE_NAMES[0] == "devbox.yaml"  # Preferred name first

    def test_default_log_driver(self):
        assert DEFAULT_LOG_DRIVER == "json-file"


class TestSecurityConfig:
    """Tests for SecurityConfig."""

    def test_default_values(self):
        cfg = SecurityConfig()
        assert cfg.read_only is False
        assert cfg.no_new_privileges is False
        assert cfg.cap_drop == []
        assert cfg.cap_add == []

    def test_to_docker_args_empty(self):
        cfg = SecurityConfig()
        assert cfg.to_docker_args() == []

    def test_to_docker_args_full(self):
        cfg = SecurityConfig(
            read_only=True,
            no_new_privileges=True,
            cap_drop=["ALL"],
            cap_add=["NET_BIND_SERVICE"],
        )
        args = cfg.to_docker_args()
        assert "--read-only" in args
        assert "--security-opt=no-new-privileges:true" in args
        assert "--cap-drop=ALL" in args
        assert "--cap-add=NET_BIND_SERVICE" in args


class TestResourcesConfig:
    """Tests for ResourcesConfig."""

    def test_default_values(self):
        cfg = ResourcesConfig()
        assert cfg.memory is None
        assert cfg.cpus is None
        assert cfg.pids_limit is None

    def test_to_docker_args_empty(self):
        cfg = ResourcesConfig()
        assert cfg.to_docker_args() == []

    def test_to_docker_args_full(self):
        cfg = ResourcesConfig(memory="512m", cpus="1.0", pids_limit=100)
        args = cfg.to_docker_args()
        assert "-m" in args
        assert "512m" in args
        assert "--cpus" in args
        assert "1.0" in args
        assert "--pids-limit" in args
        assert "100" in args


class TestLoggingConfig:
    """Tests for LoggingConfig."""

    def test_default_values(self):
        cfg = LoggingConfig()
        assert cfg.driver is None  # Default is None (use Docker default)
        assert cfg.options == {}

    def test_to_docker_args(self):
        cfg = LoggingConfig(
            driver="json-file",
            options={"max-size": "10m", "max-file": "3"},
        )
        args = cfg.to_docker_args()
        assert "--log-driver=json-file" in args
        assert "--log-opt=max-size=10m" in args
        assert "--log-opt=max-file=3" in args


class TestRunConfig:
    """Tests for RunConfig."""

    def test_default_values(self):
        cfg = RunConfig()
        assert isinstance(cfg.security, SecurityConfig)
        assert isinstance(cfg.resources, ResourcesConfig)
        assert isinstance(cfg.logging, LoggingConfig)
        assert cfg.ports == []
        assert cfg.volumes == []
        assert cfg.env == []
        assert cfg.extra_args == []

    def test_to_docker_args_with_ports(self):
        cfg = RunConfig(ports=["8080:80", "8443:443"])
        args = cfg.to_docker_args()
        assert "-p" in args
        assert "8080:80" in args
        assert "8443:443" in args

    def test_to_docker_args_with_volumes(self):
        cfg = RunConfig(volumes=["./data:/app/data"])
        args = cfg.to_docker_args()
        assert "-v" in args
        assert "./data:/app/data" in args

    def test_to_docker_args_with_env(self):
        cfg = RunConfig(env=["NODE_ENV=production"])
        args = cfg.to_docker_args()
        assert "-e" in args
        assert "NODE_ENV=production" in args

    def test_to_docker_args_with_tmpfs(self):
        cfg = RunConfig(tmpfs=["/tmp:size=100m", "/var/cache"])
        args = cfg.to_docker_args()
        assert "--tmpfs" in args
        assert "/tmp:size=100m" in args
        assert "/var/cache" in args


class TestParseHelpers:
    """Tests for parsing helper functions."""

    def test_parse_security_config(self):
        data = {"read_only": True, "no_new_privileges": True, "cap_drop": ["ALL"]}
        cfg = _parse_security_config(data)
        assert cfg.read_only is True
        assert cfg.no_new_privileges is True
        assert cfg.cap_drop == ["ALL"]

    def test_parse_resources_config(self):
        data = {"memory": "1g", "cpus": "2.0", "pids_limit": 100}
        cfg = _parse_resources_config(data)
        assert cfg.memory == "1g"
        assert cfg.cpus == "2.0"
        assert cfg.pids_limit == 100

    def test_parse_logging_config(self):
        data = {"driver": "json-file", "options": {"max-size": "10m"}}
        cfg = _parse_logging_config(data)
        assert cfg.driver == "json-file"
        assert cfg.options == {"max-size": "10m"}

    def test_parse_run_config(self):
        data = {
            "security": {"no_new_privileges": True},
            "resources": {"memory": "512m"},
            "ports": ["8080:80"],
        }
        cfg = _parse_run_config(data)
        assert cfg.security.no_new_privileges is True
        assert cfg.resources.memory == "512m"
        assert cfg.ports == ["8080:80"]


class TestDevboxConfig:
    """Tests for DevboxConfig."""

    def test_default_values(self):
        cfg = DevboxConfig()
        assert isinstance(cfg.run, RunConfig)

    def test_from_dict(self):
        data = {
            "run": {
                "security": {"no_new_privileges": True},
                "resources": {"memory": "512m"},
            }
        }
        cfg = DevboxConfig.from_dict(data)
        assert cfg.run.security.no_new_privileges is True
        assert cfg.run.resources.memory == "512m"

    def test_from_file_not_exists(self):
        from pathlib import Path

        cfg = DevboxConfig.from_file(Path("/nonexistent/config.yaml"))
        assert isinstance(cfg.run, RunConfig)

    def test_from_file_valid(self, tmp_path: Path):
        config_file = tmp_path / "devbox.yaml"
        config_file.write_text(
            """
run:
  security:
    no_new_privileges: true
  resources:
    memory: "256m"
"""
        )
        cfg = DevboxConfig.from_file(config_file)
        assert cfg.run.security.no_new_privileges is True
        assert cfg.run.resources.memory == "256m"


class TestFindConfig:
    """Tests for find_config function."""

    def test_config_not_found(self, tmp_path: Path):
        flake_nix = tmp_path / "flake.nix"
        flake_nix.write_text("")
        cfg = find_config(flake_nix)
        assert isinstance(cfg, DevboxConfig)
        assert cfg.run.resources.memory is None

    def test_find_devbox_yaml(self, tmp_path: Path):
        flake_nix = tmp_path / "flake.nix"
        flake_nix.write_text("")
        devbox_yaml = tmp_path / "devbox.yaml"
        devbox_yaml.write_text("run:\n  resources:\n    memory: 512m")
        cfg = find_config(flake_nix)
        assert cfg.run.resources.memory == "512m"

    def test_find_dot_devbox_yaml(self, tmp_path: Path):
        flake_nix = tmp_path / "flake.nix"
        flake_nix.write_text("")
        config_file = tmp_path / ".devbox.yaml"
        config_file.write_text('run:\n  resources:\n    cpus: "2.0"')
        cfg = find_config(flake_nix)
        assert cfg.run.resources.cpus == "2.0"

    def test_devbox_yaml_takes_precedence(self, tmp_path: Path):
        flake_nix = tmp_path / "flake.nix"
        flake_nix.write_text("")
        (tmp_path / ".devbox.yaml").write_text("run:\n  resources:\n    memory: 256m")
        (tmp_path / "devbox.yaml").write_text("run:\n  resources:\n    memory: 512m")
        cfg = find_config(flake_nix)
        # devbox.yaml should take precedence over .devbox.yaml
        assert cfg.run.resources.memory == "512m"
