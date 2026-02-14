"""Tests for configuration merging."""

from nix_devbox.config import (
    DevboxConfig,
    merge_devbox_configs,
    _merge_two_configs,
    _merge_lists,
)


class TestMergeLists:
    """Tests for _merge_lists helper (used for extra_args)."""

    def test_merge_two_lists(self):
        result = _merge_lists(["a", "b"], ["c", "d"])
        assert result == ["a", "b", "c", "d"]

    def test_merge_removes_duplicates(self):
        result = _merge_lists(["a", "b"], ["a", "c"])
        assert result == ["a", "b", "c"]

    def test_merge_with_empty_first(self):
        result = _merge_lists([], ["a", "b"])
        assert result == ["a", "b"]

    def test_merge_with_empty_second(self):
        result = _merge_lists(["a", "b"], [])
        assert result == ["a", "b"]

    def test_merge_both_empty(self):
        result = _merge_lists([], [])
        assert result == []


class TestMergeEnv:
    """Tests for _merge_env helper - key-based merging."""

    def test_merge_no_conflict(self):
        """Different keys should be merged."""
        from nix_devbox.config import _merge_env

        result = _merge_env(["KEY1=v1"], ["KEY2=v2"])
        assert "KEY1=v1" in result
        assert "KEY2=v2" in result

    def test_merge_same_key_override(self):
        """Same key should be overridden."""
        from nix_devbox.config import _merge_env

        result = _merge_env(["KEY=v1"], ["KEY=v2"])
        assert "KEY=v2" in result
        assert "KEY=v1" not in result

    def test_merge_mixed(self):
        """Some keys overridden, some not."""
        from nix_devbox.config import _merge_env

        base = ["VAR1=p1", "VAR2=p1", "VAR3=p1"]
        override = ["VAR1=p2", "VAR2=p2"]
        result = _merge_env(base, override)

        assert "VAR1=p2" in result
        assert "VAR2=p2" in result
        assert "VAR3=p1" in result
        assert "VAR1=p1" not in result
        assert "VAR2=p1" not in result


class TestMergePorts:
    """Tests for _merge_ports helper - host port-based merging."""

    def test_merge_no_conflict(self):
        """Different host ports should be merged."""
        from nix_devbox.config import _merge_ports

        result = _merge_ports(["8080:80"], ["3000:3000"])
        assert "8080:80" in result
        assert "3000:3000" in result

    def test_merge_same_host_port_override(self):
        """Same host port should be overridden."""
        from nix_devbox.config import _merge_ports

        result = _merge_ports(["8080:80"], ["8080:8080"])
        assert "8080:8080" in result
        assert "8080:80" not in result

    def test_merge_with_host_only(self):
        """Host-only port format."""
        from nix_devbox.config import _merge_ports

        result = _merge_ports(["8080"], ["8080:80"])
        assert "8080:80" in result
        assert "8080" not in result


class TestMergeTmpfs:
    """Tests for _merge_tmpfs helper - path-based merging."""

    def test_merge_no_conflict(self):
        """Different paths should be merged."""
        from nix_devbox.config import _merge_tmpfs

        result = _merge_tmpfs(["/tmp:size=100m"], ["/var/cache"])
        assert "/tmp:size=100m" in result
        assert "/var/cache" in result

    def test_merge_same_path_override(self):
        """Same path should be overridden."""
        from nix_devbox.config import _merge_tmpfs

        result = _merge_tmpfs(["/tmp:size=100m"], ["/tmp:size=200m"])
        assert "/tmp:size=200m" in result
        assert "/tmp:size=100m" not in result

    def test_merge_mixed(self):
        """Some paths overridden, some not."""
        from nix_devbox.config import _merge_tmpfs

        base = ["/tmp:size=100m", "/var/cache:size=50m", "/run"]
        override = ["/tmp:size=200m", "/run:size=100m"]
        result = _merge_tmpfs(base, override)

        # /tmp and /run overridden
        assert "/tmp:size=200m" in result
        assert "/run:size=100m" in result
        # /var/cache preserved
        assert "/var/cache:size=50m" in result
        # Old values gone
        assert "/tmp:size=100m" not in result
        assert "/run" not in result

    def test_merge_empty(self):
        """Empty lists handled correctly."""
        from nix_devbox.config import _merge_tmpfs

        assert _merge_tmpfs([], ["/tmp"]) == ["/tmp"]
        assert _merge_tmpfs(["/tmp"], []) == ["/tmp"]
        assert _merge_tmpfs([], []) == []


class TestMergeVolumes:
    """Tests for _merge_volumes helper - container path based merging."""

    def test_merge_no_conflict(self):
        """Different container paths should be merged."""
        from nix_devbox.config import _merge_volumes

        result = _merge_volumes(["./data:/app/data"], ["./logs:/app/logs"])
        assert "./data:/app/data" in result
        assert "./logs:/app/logs" in result

    def test_merge_same_container_path_override(self):
        """Same container path should be overridden."""
        from nix_devbox.config import _merge_volumes

        result = _merge_volumes(["./host1:/app/data"], ["./host2:/app/data"])
        assert "./host2:/app/data" in result
        assert "./host1:/app/data" not in result

    def test_merge_with_options(self):
        """Container path with options."""
        from nix_devbox.config import _merge_volumes

        result = _merge_volumes(["./data:/app/data:ro"], ["./new:/app/data:rw"])
        assert "./new:/app/data:rw" in result
        assert "./data:/app/data:ro" not in result


class TestMergeTwoConfigs:
    """Tests for _merge_two_configs."""

    def test_resources_override(self):
        base = DevboxConfig.from_dict(
            {"run": {"resources": {"memory": "512m", "cpus": "1.0"}}}
        )
        override = DevboxConfig.from_dict(
            {"run": {"resources": {"memory": "1g"}}}  # Override memory
        )

        merged = _merge_two_configs(base, override)

        assert merged.run.resources.memory == "1g"  # Overridden
        assert merged.run.resources.cpus == "1.0"  # Preserved

    def test_security_boolean_or(self):
        base = DevboxConfig.from_dict(
            {"run": {"security": {"read_only": False, "no_new_privileges": False}}}
        )
        override = DevboxConfig.from_dict(
            {"run": {"security": {"no_new_privileges": True}}}
        )

        merged = _merge_two_configs(base, override)

        assert merged.run.security.read_only is False
        assert merged.run.security.no_new_privileges is True

    def test_security_cap_merge(self):
        base = DevboxConfig.from_dict(
            {
                "run": {
                    "security": {
                        "cap_drop": ["ALL"],
                        "cap_add": ["NET_BIND_SERVICE"],
                    }
                }
            }
        )
        override = DevboxConfig.from_dict(
            {"run": {"security": {"cap_add": ["SYS_PTRACE"]}}}
        )

        merged = _merge_two_configs(base, override)

        assert "ALL" in merged.run.security.cap_drop
        assert "NET_BIND_SERVICE" in merged.run.security.cap_add
        assert "SYS_PTRACE" in merged.run.security.cap_add

    def test_logging_options_merge(self):
        base = DevboxConfig.from_dict(
            {"run": {"logging": {"options": {"max-size": "10m"}}}}
        )
        override = DevboxConfig.from_dict(
            {"run": {"logging": {"options": {"max-file": "3"}}}}
        )

        merged = _merge_two_configs(base, override)

        assert merged.run.logging.options == {"max-size": "10m", "max-file": "3"}

    def test_lists_merge(self):
        base = DevboxConfig.from_dict(
            {
                "run": {
                    "ports": ["8080:80"],
                    "volumes": ["./data:/data"],
                    "env": ["KEY1=value1"],
                    "tmpfs": ["/tmp"],
                }
            }
        )
        override = DevboxConfig.from_dict(
            {
                "run": {
                    "ports": ["3000:3000"],
                    "volumes": ["./logs:/logs"],
                    "env": ["KEY2=value2"],
                    "tmpfs": ["/var/cache"],
                }
            }
        )

        merged = _merge_two_configs(base, override)

        assert "8080:80" in merged.run.ports
        assert "3000:3000" in merged.run.ports
        assert "./data:/data" in merged.run.volumes
        assert "./logs:/logs" in merged.run.volumes
        assert "KEY1=value1" in merged.run.env
        assert "KEY2=value2" in merged.run.env
        assert "/tmp" in merged.run.tmpfs
        assert "/var/cache" in merged.run.tmpfs


class TestMergeDevboxConfigs:
    """Tests for merge_devbox_configs."""

    def test_empty_list_returns_default(self):
        result = merge_devbox_configs([])
        assert result == DevboxConfig()

    def test_single_config_returns_self(self):
        config = DevboxConfig.from_dict({"run": {"resources": {"memory": "1g"}}})
        result = merge_devbox_configs([config])
        assert result.run.resources.memory == "1g"

    def test_multiple_configs_merge_in_order(self):
        config1 = DevboxConfig.from_dict(
            {"run": {"resources": {"memory": "512m"}, "ports": ["8080:80"]}}
        )
        config2 = DevboxConfig.from_dict(
            {"run": {"resources": {"cpus": "2.0"}, "ports": ["3000:3000"]}}
        )
        config3 = DevboxConfig.from_dict({"run": {"env": ["KEY=value"]}})

        merged = merge_devbox_configs([config1, config2, config3])

        assert merged.run.resources.memory == "512m"
        assert merged.run.resources.cpus == "2.0"
        assert "8080:80" in merged.run.ports
        assert "3000:3000" in merged.run.ports
        assert "KEY=value" in merged.run.env

    def test_image_override(self):
        """Later config's image should override earlier config's image."""
        base = DevboxConfig.from_dict({"image": "base-image:latest"})
        override = DevboxConfig.from_dict({"image": "override-image:v2"})

        merged = _merge_two_configs(base, override)

        assert merged.image == "override-image:v2"

    def test_image_inheritance(self):
        """If override doesn't specify image, base's image should be used."""
        base = DevboxConfig.from_dict({"image": "base-image:latest"})
        override = DevboxConfig.from_dict({"run": {"resources": {"memory": "1g"}}})

        merged = _merge_two_configs(base, override)

        assert merged.image == "base-image:latest"

    def test_multiple_configs_image_merge(self):
        """Image from last config should take precedence."""
        config1 = DevboxConfig.from_dict({"image": "image1:v1"})
        config2 = DevboxConfig.from_dict({"run": {"resources": {"memory": "512m"}}})
        config3 = DevboxConfig.from_dict({"image": "image3:v3"})

        merged = merge_devbox_configs([config1, config2, config3])

        assert merged.image == "image3:v3"


class TestMergeInitConfig:
    """Tests for init configuration merging."""

    def test_init_commands_merge(self):
        """Init commands should be merged (not overridden)."""
        base = DevboxConfig.from_dict(
            {"init": {"commands": ["mkdir -p /workspace", "chmod 777 /workspace"]}}
        )
        override = DevboxConfig.from_dict(
            {"init": {"commands": ["mkdir -p /build", "chmod 777 /build"]}}
        )

        merged = _merge_two_configs(base, override)

        # Both sets of commands should be present
        assert "mkdir -p /workspace" in merged.init.commands
        assert "chmod 777 /workspace" in merged.init.commands
        assert "mkdir -p /build" in merged.init.commands
        assert "chmod 777 /build" in merged.init.commands

    def test_init_commands_deduplication(self):
        """Duplicate commands should be removed."""
        base = DevboxConfig.from_dict({"init": {"commands": ["mkdir -p /workspace"]}})
        override = DevboxConfig.from_dict(
            {"init": {"commands": ["mkdir -p /workspace", "chmod 777 /build"]}}
        )

        merged = _merge_two_configs(base, override)

        # Duplicate command should appear only once
        assert merged.init.commands.count("mkdir -p /workspace") == 1
        assert "chmod 777 /build" in merged.init.commands

    def test_multiple_configs_init_merge(self):
        """Multiple configs should merge init commands in order."""
        config1 = DevboxConfig.from_dict({"init": {"commands": ["echo 'config1'"]}})
        config2 = DevboxConfig.from_dict({"init": {"commands": ["echo 'config2'"]}})
        config3 = DevboxConfig.from_dict({"init": {"commands": ["echo 'config3'"]}})

        merged = merge_devbox_configs([config1, config2, config3])

        # All commands from all configs should be present
        assert "echo 'config1'" in merged.init.commands
        assert "echo 'config2'" in merged.init.commands
        assert "echo 'config3'" in merged.init.commands

    def test_empty_init_config(self):
        """Empty init config should not affect merged result."""
        base = DevboxConfig.from_dict({"init": {"commands": ["mkdir -p /workspace"]}})
        override = DevboxConfig.from_dict({})  # No init config

        merged = _merge_two_configs(base, override)

        # Base commands should be preserved
        assert "mkdir -p /workspace" in merged.init.commands

    def test_run_and_init_config_together(self):
        """Both run and init configs should be merged correctly."""
        config1 = DevboxConfig.from_dict(
            {
                "run": {"resources": {"memory": "1g"}},
                "init": {"commands": ["mkdir -p /workspace"]},
            }
        )
        config2 = DevboxConfig.from_dict(
            {
                "run": {"resources": {"cpus": "2.0"}},
                "init": {"commands": ["chmod 777 /workspace"]},
            }
        )

        merged = merge_devbox_configs([config1, config2])

        # Both run configs merged
        assert merged.run.resources.memory == "1g"
        assert merged.run.resources.cpus == "2.0"

        # Both init commands merged
        assert "mkdir -p /workspace" in merged.init.commands
        assert "chmod 777 /workspace" in merged.init.commands
