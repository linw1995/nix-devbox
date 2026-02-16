"""Build hooks for pdm-backend."""

import subprocess
from pathlib import Path


def get_git_info():
    """Get git commit sha and dirty status."""
    try:
        project_root = Path(__file__).parent

        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=project_root,
            capture_output=True,
            text=True,
            check=True,
        )
        sha = result.stdout.strip()[:7]

        diff_result = subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=no"],
            cwd=project_root,
            capture_output=True,
            text=True,
            check=False,
        )
        is_dirty = bool(diff_result.stdout.strip())

        return sha, is_dirty
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unknown", False


def pdm_build_initialize(context):
    """Update _version.py with git info before build."""
    sha, is_dirty = get_git_info()

    # Only update if we have valid git info
    if not sha or sha == "unknown":
        return

    project_root = Path(__file__).parent
    version_path = project_root / "src" / "nix_devbox" / "_version.py"
    version_path.write_text(f'__commit_sha__ = "{sha}"\n__is_dirty__ = {is_dirty}\n')
    print(f"Updated: sha={sha}, dirty={is_dirty}")
