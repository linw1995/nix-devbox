"""Test environment variable expansion with escape support."""

import os
import sys
import tempfile

sys.path.insert(0, "src")

from nix_devbox.config import expand_env_vars, expand_env_vars_in_list, DevboxConfig


def test_expand_simple_variable():
    """Test expanding $VAR syntax."""
    os.environ["TEST_VAR"] = "test_value"
    assert expand_env_vars("/path/$TEST_VAR/file") == "/path/test_value/file"


def test_expand_braced_variable():
    """Test expanding ${VAR} syntax."""
    os.environ["TEST_VAR2"] = "test_value2"
    assert expand_env_vars("/path/${TEST_VAR2}/file") == "/path/test_value2/file"


def test_expand_unknown_variable():
    """Test that unknown variables are left unchanged."""
    result = expand_env_vars("/path/$UNKNOWN_VAR/file")
    assert result == "/path/$UNKNOWN_VAR/file"


def test_expand_in_list():
    """Test expanding variables in a list of strings."""
    os.environ["TEST_LIST_VAR"] = "list_value"
    input_list = ["/path/$TEST_LIST_VAR", "plain_string"]
    result = expand_env_vars_in_list(input_list)
    assert result == ["/path/list_value", "plain_string"]


def test_expand_in_list_with_none():
    """Test that None input returns empty list."""
    result = expand_env_vars_in_list(None)
    assert result == []
    assert isinstance(result, list)


def test_expand_escaped_dollar():
    r"""Test that \\$ is treated as literal $ and not expanded."""
    os.environ["ESCAPED_VAR"] = "should_not_expand"
    # $$VAR should become $VAR (literal), not expand
    result = expand_env_vars("/path/$$ESCAPED_VAR/file")
    assert result == "/path/$ESCAPED_VAR/file"


def test_expand_escaped_braced():
    """Test that $${VAR} is treated as literal ${VAR}."""
    os.environ["ESCAPED_BRACED"] = "should_not_expand"
    # $${VAR} should become ${VAR} (literal)
    result = expand_env_vars("/path/$${ESCAPED_BRACED}/file")
    assert result == "/path/${ESCAPED_BRACED}/file"


def test_expand_mixed_escaped_and_normal():
    """Test mixing escaped and normal variables."""
    os.environ["NORMAL_VAR"] = "normal_value"
    # $$ESCAPED stays as $ESCAPED, $NORMAL_VAR expands
    result = expand_env_vars("/path/$$ESCAPED/$NORMAL_VAR/file")
    assert result == "/path/$ESCAPED/normal_value/file"


def test_expand_escaped_unknown_variable():
    """Test that $$UNKNOWN becomes $UNKNOWN (literal)."""
    result = expand_env_vars("/path/$$UNKNOWN/file")
    assert result == "/path/$UNKNOWN/file"


def test_config_from_file_with_expansion():
    """Test that expansion happens when loading from file."""
    os.environ["CONFIG_VAR"] = "config_value"

    yaml_content = """
run:
  volumes:
    - /host/$CONFIG_VAR:/container/path
"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write(yaml_content)
        f.flush()
        config = DevboxConfig.from_file(f.name)
        os.unlink(f.name)

    assert "/host/config_value:/container/path" in config.run.volumes


def test_config_from_file_with_escape():
    """Test that $$ is preserved as literal $ in config file."""
    yaml_content = """
run:
  volumes:
    - /host/$$LITERAL:/container/path
"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write(yaml_content)
        f.flush()
        config = DevboxConfig.from_file(f.name)
        os.unlink(f.name)

    assert "/host/$LITERAL:/container/path" in config.run.volumes


if __name__ == "__main__":
    # Run all tests
    test_functions = [
        test_expand_simple_variable,
        test_expand_braced_variable,
        test_expand_unknown_variable,
        test_expand_in_list,
        test_expand_in_list_with_none,
        test_expand_escaped_dollar,
        test_expand_escaped_braced,
        test_expand_mixed_escaped_and_normal,
        test_expand_escaped_unknown_variable,
        test_config_from_file_with_expansion,
        test_config_from_file_with_escape,
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
