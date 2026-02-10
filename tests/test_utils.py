"""Tests for utility functions."""

from nix_devbox.utils import expand_flagged_options


class TestExpandFlaggedOptions:
    """Tests for expand_flagged_options utility function."""

    def test_basic_expansion(self):
        """Test basic flag-value expansion."""
        result = expand_flagged_options("-p", ["8080:80", "8443:443"])
        assert result == ["-p", "8080:80", "-p", "8443:443"]

    def test_single_item(self):
        """Test with single item."""
        result = expand_flagged_options("-e", ["KEY=value"])
        assert result == ["-e", "KEY=value"]

    def test_empty_list(self):
        """Test with empty list returns empty."""
        result = expand_flagged_options("-v", [])
        assert result == []

    def test_none_returns_empty(self):
        """Test with None returns empty."""
        result = expand_flagged_options("-p", None)
        assert result == []

    def test_different_flags(self):
        """Test with different flag types."""
        # Long flags
        result = expand_flagged_options("--volume", ["/data:/data"])
        assert result == ["--volume", "/data:/data"]

        # Short flags
        result = expand_flagged_options("-v", ["/data:/data"])
        assert result == ["-v", "/data:/data"]
