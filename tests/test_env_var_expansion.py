"""Test configuration value passing (no expansion in Python)."""

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, "src")

from nix_devbox.config import DevboxConfig


def test_config_from_file_values_preserved():
    """Test that values are passed through as-is (no expansion)."""
    yaml_content = """
run:
  volumes:
    - /host/$CONFIG_VAR:/container/path
    - /host/$${LITERAL}:/container/path2
"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write(yaml_content)
        f.flush()
        config_path = Path(f.name)
        config = DevboxConfig.from_file(config_path)
        config_path.unlink()

    # Values are kept as-is for shell expansion during docker run
    assert "/host/$CONFIG_VAR:/container/path" in config.run.volumes
    assert "/host/$${LITERAL}:/container/path2" in config.run.volumes


def test_env_values_preserved():
    """Test that env values are passed through as-is."""
    yaml_content = """
run:
  env:
    - KEY=$VALUE
    - BUILD_TIME=$(date)
"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write(yaml_content)
        f.flush()
        config_path = Path(f.name)
        config = DevboxConfig.from_file(config_path)
        config_path.unlink()

    assert "KEY=$VALUE" in config.run.env
    assert "BUILD_TIME=$(date)" in config.run.env


if __name__ == "__main__":
    test_functions = [
        test_config_from_file_values_preserved,
        test_env_values_preserved,
    ]

    passed = 0
    failed = 0
    for test_func in test_functions:
        try:
            test_func()
            print(f"✅ {test_func.__name__}")
            passed += 1
        except AssertionError as e:
            print(f"❌ {test_func.__name__}: {e}")
            failed += 1
        except Exception as e:
            print(f"💥 {test_func.__name__}: {e}")
            failed += 1

    print()
    print(f"Results: {passed} passed, {failed} failed")
    sys.exit(0 if failed == 0 else 1)
