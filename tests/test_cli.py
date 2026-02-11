"""Tests for CLI module."""

from nix_devbox.cli import _collect_parent_dirs, _extract_container_path


class TestExtractContainerPath:
    """Tests for _extract_container_path function."""

    def test_basic_volume(self):
        """Extract container path from basic volume mapping."""
        assert _extract_container_path("/host:/container") == "/container"

    def test_volume_with_options(self):
        """Extract container path from volume with options."""
        assert _extract_container_path("/host:/container:rw") == "/container"

    def test_relative_path_host(self):
        """Extract container path from relative host path."""
        assert _extract_container_path("./host:/container") == "/container"

    def test_env_var_host(self):
        """Extract container path from env var host path."""
        assert _extract_container_path("$HOME:/container") == "/container"

    def test_home_dir_host(self):
        """Extract container path from home dir host path."""
        assert _extract_container_path("~/.config:/container") == "/container"

    def test_named_volume(self):
        """Named volumes should return None."""
        assert _extract_container_path("named_volume:/container") is None

    def test_tmpfs(self):
        """Tmpfs mounts should return None."""
        assert _extract_container_path("tmpfs:/tmp") is None

    def test_invalid_format(self):
        """Invalid format should return None."""
        assert _extract_container_path("/invalid_no_colon") is None


class TestCollectParentDirs:
    """Tests for _collect_parent_dirs function."""

    def test_single_volume(self):
        """Single volume should collect parent directories."""
        volumes = ["/host:/build/.config/app"]
        result = _collect_parent_dirs(volumes)
        assert "/build/.config" in result
        assert "/build" not in result  # /build is the stop point

    def test_multiple_volumes_same_parent(self):
        """Multiple volumes sharing same parent should deduplicate."""
        volumes = [
            "/host1:/build/.config/app1",
            "/host2:/build/.config/app2",
        ]
        result = _collect_parent_dirs(volumes)
        # Should have /build/.config only once
        assert result.count("/build/.config") == 1
        assert "/build/.config" in result

    def test_nested_volumes_parent_is_mount_point(self):
        """When parent directory is itself a mount point, exclude it."""
        volumes = [
            "/host:/build/.config",  # Parent mount point
            "/host/app:/build/.config/app",  # Child mount point
        ]
        result = _collect_parent_dirs(volumes)
        # /build/.config is a mount point, should not be in parent_dirs
        assert "/build/.config" not in result
        # /build is the parent of the parent mount point
        assert "/build" not in result  # Stop at /build

    def test_deeply_nested_volumes(self):
        """Test deeply nested volume structure."""
        volumes = [
            "/a:/build/a",
            "/a/b:/build/a/b",
            "/a/b/c:/build/a/b/c",
        ]
        result = _collect_parent_dirs(volumes)
        # /build/a is a mount point, exclude from parent_dirs
        assert "/build/a" not in result
        # /build/a/b is a mount point, exclude from parent_dirs
        assert "/build/a/b" not in result
        # /build is stop point
        assert "/build" not in result

    def test_sibling_volumes(self):
        """Test sibling volumes under same parent."""
        volumes = [
            "/host/config:/build/.config",
            "/host/cache:/build/.cache",
        ]
        result = _collect_parent_dirs(volumes)
        # Both are mount points, should not be in parent_dirs
        assert "/build/.config" not in result
        assert "/build/.cache" not in result
        # /build is stop point
        assert "/build" not in result

    def test_mixed_mount_and_parent(self):
        """Test mix where some paths are parents and some are mount points."""
        volumes = [
            "/host:/build/data",  # Mount point
            "/host/sub:/build/data/sub/dir",  # Deep mount point
        ]
        result = _collect_parent_dirs(volumes)
        # /build/data is a mount point, exclude
        assert "/build/data" not in result
        # /build/data/sub is parent of deep mount point but not a mount point itself
        assert "/build/data/sub" in result

    def test_empty_volumes(self):
        """Empty volumes list should return empty list."""
        assert _collect_parent_dirs([]) == []

    def test_named_volumes_ignored(self):
        """Named volumes should be ignored in parent dir collection."""
        volumes = [
            "named_vol:/build/data",  # Named volume, ignored
            "/host:/build/config",  # Bind mount
        ]
        result = _collect_parent_dirs(volumes)
        # /build/data parent is /build, which is stop point
        # /build/config is a mount point
        assert "/build/config" not in result

    def test_sorting_order(self):
        """Result should be sorted by depth (shorter paths first)."""
        volumes = [
            "/host:/build/a/b/c/d",
        ]
        result = _collect_parent_dirs(volumes)
        # Should be sorted: /build/a, /build/a/b, /build/a/b/c
        expected_order = ["/build/a", "/build/a/b", "/build/a/b/c"]
        # Filter to only get the ones we expect
        filtered = [p for p in result if p in expected_order]
        assert filtered == expected_order
