"""Configuration file parsing for nix-devbox."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, TypeVar

import yaml

from .exceptions import ConfigError
from .utils import extract_part_by_separator

# Configuration file names to look for, in order of preference
CONFIG_FILE_NAMES = ("devbox.yaml", ".devbox.yaml", "devbox.yml", ".devbox.yml")

# Docker defaults
DEFAULT_LOG_DRIVER = "json-file"


@dataclass(frozen=True)
class SecurityConfig:
    """Security-related docker run options."""

    read_only: bool = False
    no_new_privileges: bool = False
    cap_drop: list[str] = field(default_factory=list)
    cap_add: list[str] = field(default_factory=list)

    def to_docker_args(self) -> list[str]:
        """Convert security config to docker run arguments."""
        args = []
        if self.read_only:
            args.append("--read-only")
        if self.no_new_privileges:
            args.append("--security-opt=no-new-privileges:true")
        for cap in self.cap_drop:
            args.append(f"--cap-drop={cap}")
        for cap in self.cap_add:
            args.append(f"--cap-add={cap}")
        return args


@dataclass(frozen=True)
class ResourcesConfig:
    """Resource limits for docker run."""

    memory: str | None = None
    cpus: str | None = None
    pids_limit: int | None = None

    def to_docker_args(self) -> list[str]:
        """Convert resources config to docker run arguments."""
        args = []
        if self.memory:
            args.extend(["-m", self.memory])
        if self.cpus:
            args.extend(["--cpus", self.cpus])
        if self.pids_limit:
            args.extend(["--pids-limit", str(self.pids_limit)])
        return args


@dataclass(frozen=True)
class LoggingConfig:
    """Logging configuration for docker run."""

    # Use None to indicate "not explicitly set" (will use Docker default)
    # This allows distinguishing between "not set" and "explicitly set to json-file"
    driver: str | None = None
    options: dict[str, str] = field(default_factory=dict)

    def to_docker_args(self) -> list[str]:
        """Convert logging config to docker run arguments."""
        args = []
        # Only set log driver if explicitly configured
        if self.driver is not None:
            args.append(f"--log-driver={self.driver}")
        for key, value in self.options.items():
            args.append(f"--log-opt={key}={value}")
        return args

    def is_driver_explicitly_set(self) -> bool:
        """Check if driver was explicitly set (not default None)."""
        return self.driver is not None


@dataclass(frozen=True)
class RunConfig:
    """Docker run configuration for devshell environments."""

    security: SecurityConfig = field(default_factory=SecurityConfig)
    resources: ResourcesConfig = field(default_factory=ResourcesConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    ports: list[str] = field(default_factory=list)
    volumes: list[str] = field(default_factory=list)
    env: list[str] = field(default_factory=list)
    tmpfs: list[str] = field(default_factory=list)
    extra_args: list[str] = field(default_factory=list)
    user: str | None = None

    def _to_non_list_docker_args(self) -> list[str]:
        """Convert non-list config options to docker arguments.

        List configs (ports, volumes, env, tmpfs) are handled separately.
        """
        args = []
        args.extend(self.security.to_docker_args())
        args.extend(self.resources.to_docker_args())
        args.extend(self.logging.to_docker_args())
        if self.user:
            args.append(f"--user={self.user}")
        return args

    def to_docker_args(self) -> list[str]:
        """Convert all config options to docker run arguments.

        Note: Values are returned as-is for shell variable expansion.
        """
        args = self._to_non_list_docker_args()

        # Add list options
        for port in self.ports:
            args.extend(["-p", port])
        for volume in self.volumes:
            args.extend(["-v", volume])
        for e in self.env:
            args.extend(["-e", e])
        for tmp in self.tmpfs:
            args.extend(["--tmpfs", tmp])
        for arg in self.extra_args:
            args.append(arg)

        return args


T = TypeVar("T")


def _parse_security_config(data: dict[str, Any] | None) -> SecurityConfig:
    """Parse security configuration from dict."""
    if data is None:
        return SecurityConfig()
    return SecurityConfig(
        read_only=data.get("read_only", False),
        no_new_privileges=data.get("no_new_privileges", False),
        cap_drop=data.get("cap_drop", []),
        cap_add=data.get("cap_add", []),
    )


def _parse_resources_config(data: dict[str, Any] | None) -> ResourcesConfig:
    """Parse resources configuration from dict."""
    if data is None:
        return ResourcesConfig()
    # cpus must be string (Docker CLI requirement)
    cpus = data.get("cpus")
    return ResourcesConfig(
        memory=data.get("memory"),
        cpus=str(cpus) if cpus is not None else None,
        pids_limit=data.get("pids_limit"),
    )


def _parse_logging_config(data: dict[str, Any] | None) -> LoggingConfig:
    """Parse logging configuration from dict."""
    if data is None:
        return LoggingConfig()
    return LoggingConfig(
        driver=data.get("driver"),
        options=data.get("options", {}),
    )


def _parse_run_config(data: dict[str, Any]) -> RunConfig:
    """Parse run configuration from dict.

    Note: Values are passed through as-is. Shell variable expansion
    ($VAR, $(cmd)) is handled by the shell when executing docker run.
    """
    # Get user config: if not specified, leave as None
    # The entrypoint will handle user switching automatically
    user = data.get("user")

    return RunConfig(
        security=_parse_security_config(data.get("security")),
        resources=_parse_resources_config(data.get("resources")),
        logging=_parse_logging_config(data.get("logging")),
        ports=data.get("ports", []),
        volumes=data.get("volumes", []),
        env=data.get("env", []),
        tmpfs=data.get("tmpfs", []),
        extra_args=data.get("extra_args", []),
        user=user,
    )


@dataclass(frozen=True)
class InitConfig:
    """Container initialization configuration (runs on container start)."""

    # Directories to ensure exist (created by root before chown)
    # Useful for XDG directories that aren't explicitly mounted
    ensure_dirs: list[str] = field(default_factory=list)

    # Commands to run when container starts (before the main command)
    # These run as the container user (not root, unless user: "0:0")
    commands: list[str] = field(default_factory=list)


def _parse_init_config(data: dict[str, Any] | None) -> InitConfig:
    """Parse init configuration from dict."""
    if data is None:
        return InitConfig()
    return InitConfig(
        ensure_dirs=data.get("ensure_dirs", []),
        commands=data.get("commands", []),
    )


@dataclass(frozen=True)
class DevboxConfig:
    """Complete devbox configuration."""

    run: RunConfig = field(default_factory=RunConfig)
    init: InitConfig = field(default_factory=InitConfig)

    @classmethod
    def from_file(cls, path: Path) -> "DevboxConfig":
        """Load configuration from a YAML file.

        Args:
            path: Path to the YAML configuration file

        Returns:
            DevboxConfig instance

        Raises:
            ConfigError: If file cannot be read or parsed
        """
        try:
            with open(path, encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
        except FileNotFoundError:
            return cls()
        except yaml.YAMLError as exc:
            raise ConfigError(f"Invalid YAML in {path}: {exc}") from exc

        return cls.from_dict(data)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DevboxConfig":
        """Create DevboxConfig from a dictionary."""
        run_data = data.get("run", {})
        init_data = data.get("init", {})

        return cls(
            run=_parse_run_config(run_data),
            init=_parse_init_config(init_data),
        )


def find_config(start_path: Path) -> DevboxConfig:
    """Find and load devbox configuration.

    Searches for configuration files in order of preference:
    1. devbox.yaml
    2. .devbox.yaml
    3. devbox.yml
    4. .devbox.yml

    Args:
        start_path: Path to start searching from (should be flake.nix directory)

    Returns:
        DevboxConfig instance (empty config if no file found)
    """
    for filename in CONFIG_FILE_NAMES:
        config_path = start_path.parent / filename
        if config_path.exists():
            return DevboxConfig.from_file(config_path)

    return DevboxConfig()


def merge_devbox_configs(configs: list[DevboxConfig]) -> DevboxConfig:
    """Merge multiple DevboxConfigs into one.

    Merge strategy:
    - Scalar values (memory, cpus, etc.): Later configs override earlier ones
    - Boolean flags (read_only, no_new_privileges): Later configs override earlier ones
    - List values (ports, volumes, env, tmpfs, cap_drop, cap_add): Merge all lists
    - Dict values (logging.options): Later configs override earlier ones

    Args:
        configs: List of DevboxConfigs to merge (in priority order)

    Returns:
        Merged DevboxConfig
    """
    if not configs:
        return DevboxConfig()

    if len(configs) == 1:
        return configs[0]

    # Start with the first config
    merged = configs[0]

    for config in configs[1:]:
        merged = _merge_two_configs(merged, config)

    return merged


# Generic type variable for the pick helper
_T = TypeVar("_T")


def _pick_override_or_base(override_value: _T | None, base_value: _T) -> _T:
    """Return override_value if set, otherwise base_value.

    This is a generic helper for merging scalar config values where
    the override takes precedence over the base.
    """
    return override_value if override_value is not None else base_value


def _merge_two_configs(base: DevboxConfig, override: DevboxConfig) -> DevboxConfig:
    """Merge two DevboxConfigs, with override taking precedence."""
    base_run = base.run
    override_run = override.run

    # Merge security config - override takes precedence
    merged_security = SecurityConfig(
        read_only=override_run.security.read_only,
        no_new_privileges=override_run.security.no_new_privileges,
        cap_drop=_merge_lists(
            base_run.security.cap_drop, override_run.security.cap_drop
        ),
        cap_add=_merge_lists(base_run.security.cap_add, override_run.security.cap_add),
    )

    # Merge resources config - override takes precedence for scalars
    merged_resources = ResourcesConfig(
        memory=_pick_override_or_base(
            override_run.resources.memory, base_run.resources.memory
        ),
        cpus=_pick_override_or_base(
            override_run.resources.cpus, base_run.resources.cpus
        ),
        pids_limit=_pick_override_or_base(
            override_run.resources.pids_limit, base_run.resources.pids_limit
        ),
    )

    # Merge logging config - override takes precedence
    # If override has explicit driver, use it; otherwise inherit from base
    merged_driver = (
        override_run.logging.driver
        if override_run.logging.is_driver_explicitly_set()
        else base_run.logging.driver
    )
    merged_logging = LoggingConfig(
        driver=merged_driver,
        options={**base_run.logging.options, **override_run.logging.options},
    )

    # Merge list fields
    # Note: volumes and tmpfs use path-based merging (override for same paths)
    # ports and env also use key-based merging
    merged_run = RunConfig(
        security=merged_security,
        resources=merged_resources,
        logging=merged_logging,
        ports=_merge_ports(base_run.ports, override_run.ports),
        volumes=_merge_volumes(base_run.volumes, override_run.volumes),
        env=_merge_env(base_run.env, override_run.env),
        tmpfs=_merge_tmpfs(base_run.tmpfs, override_run.tmpfs),
        extra_args=_merge_lists(base_run.extra_args, override_run.extra_args),
        user=_pick_override_or_base(override_run.user, base_run.user),
    )

    # Merge init config - merge ensure_dirs and commands lists
    base_init = base.init
    override_init = override.init
    merged_init = InitConfig(
        ensure_dirs=_merge_lists(base_init.ensure_dirs, override_init.ensure_dirs),
        commands=_merge_lists(base_init.commands, override_init.commands),
    )

    return DevboxConfig(run=merged_run, init=merged_init)


def _merge_lists(base: list[str], override: list[str]) -> list[str]:
    """Merge two lists, removing duplicates while preserving order.

    Items from override are appended after base items.
    """
    if not base:
        return list(override)
    if not override:
        return list(base)

    # Use dict.fromkeys() to preserve order and remove duplicates
    # This is more concise and Pythonic than manual set tracking
    return list(dict.fromkeys(base + override))


def _extract_volume_container_path(volume: str) -> str:
    """Extract container path from volume specification.

    Args:
        volume: Volume mount spec like './host:/container:ro'

    Returns:
        Container path (e.g., '/container')
    """
    return extract_part_by_separator(volume, ":", 1)


def _extract_tmpfs_path(tmpfs: str) -> str:
    """Extract mount path from tmpfs specification.

    Args:
        tmpfs: Tmpfs mount spec like '/tmp:size=100m,mode=1777'

    Returns:
        Mount path (e.g., '/tmp')
    """
    return extract_part_by_separator(tmpfs, ":", 0)


def _extract_port_key(port: str) -> str:
    """Extract host port from port mapping for merging.

    Args:
        port: Port mapping like '8080:80' or just '8080'

    Returns:
        Host port (e.g., '8080')
    """
    return extract_part_by_separator(port, ":", 0)


def _extract_env_key(env: str) -> str:
    """Extract variable name from env var for merging.

    Args:
        env: Env var like 'KEY=value' or just 'KEY'

    Returns:
        Variable name (e.g., 'KEY')
    """
    return extract_part_by_separator(env, "=", 0)


def _merge_by_key(
    base: list[str],
    override: list[str],
    key_func: Callable[[str], str],
) -> list[str]:
    """Merge two lists, with override taking precedence for items with same key.

    This is a generic merge function used by volume, tmpfs, port, and env merging.
    Items from override replace items from base that have the same key.

    Args:
        base: Base list from earlier config
        override: Override list from later config
        key_func: Function to extract the merge key from each item

    Returns:
        Merged list with override taking precedence for same keys
    """
    if not override:
        return list(base)
    if not base:
        return list(override)

    # Build lookup of override keys to their full values
    override_keys = {key_func(item): item for item in override}

    # Start with base items, filtering out those that are overridden
    result = [item for item in base if key_func(item) not in override_keys]

    # Append all override items (preserving order)
    result.extend(override)

    return result


# Specific merge functions using the generic _merge_by_key
def _merge_volumes(base: list[str], override: list[str]) -> list[str]:
    """Merge volume mounts by container path."""
    return _merge_by_key(base, override, _extract_volume_container_path)


def _merge_tmpfs(base: list[str], override: list[str]) -> list[str]:
    """Merge tmpfs mounts by mount path."""
    return _merge_by_key(base, override, _extract_tmpfs_path)


def _merge_ports(base: list[str], override: list[str]) -> list[str]:
    """Merge port mappings by host port."""
    return _merge_by_key(base, override, _extract_port_key)


def _merge_env(base: list[str], override: list[str]) -> list[str]:
    """Merge env vars by variable name."""
    return _merge_by_key(base, override, _extract_env_key)
