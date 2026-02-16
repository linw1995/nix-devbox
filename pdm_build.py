"""Build hooks for pdm-backend."""

import subprocess
from pathlib import Path


def get_git_info():
    """Get git commit sha and dirty status."""
    try:
        module_dir = Path(__file__).parent / "src" / "nix_devbox"

        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=module_dir,
            capture_output=True,
            text=True,
            check=True,
        )
        sha = result.stdout.strip()[:7]

        diff_result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=module_dir,
            capture_output=True,
            text=True,
            check=False,
        )
        is_dirty = bool(diff_result.stdout.strip())

        return sha, is_dirty
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unknown", False


def pdm_build_initialize(context):
    """Update __init__.py with git info before build."""
    sha, is_dirty = get_git_info()

    # Only update if we have valid git info
    if not sha or sha == "unknown":
        return

    init_path = Path(__file__).parent / "src" / "nix_devbox" / "__init__.py"
    content = init_path.read_text()

    new_lines = []
    for line in content.splitlines():
        if line.startswith("__version__"):
            new_lines.append('__version__ = "0.1.0"')
        elif line.startswith("__commit_sha__"):
            new_lines.append(f'__commit_sha__ = "{sha}"')
        elif line.startswith("__is_dirty__"):
            new_lines.append(f"__is_dirty__ = {is_dirty}")
        else:
            new_lines.append(line)

    init_path.write_text("\n".join(new_lines) + "\n")
    print(f"Updated: sha={sha}, dirty={is_dirty}")
