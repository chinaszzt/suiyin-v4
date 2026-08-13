"""Resolve content-stable git tree identifiers."""

from __future__ import annotations

import subprocess
from pathlib import Path


def resolve_tree_sha(repo_root: Path, ref: str = "HEAD") -> str:
    """Return ``ref``'s git tree SHA, raising ``ValueError`` on failure."""
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_root), "rev-parse", f"{ref}^{{tree}}"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            shell=False,
            check=False,
        )
    except OSError as exc:
        raise ValueError(
            f"git rev-parse {ref}^{{tree}} failed: {str(exc).strip()[-500:]}"
        ) from exc

    tree_sha = result.stdout.strip()
    if result.returncode != 0 or not tree_sha:
        stderr_tail = result.stderr.strip()[-500:] or "no stderr output"
        raise ValueError(
            f"git rev-parse {ref}^{{tree}} failed: {stderr_tail}"
        )
    return tree_sha
