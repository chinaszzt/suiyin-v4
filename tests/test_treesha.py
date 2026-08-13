from __future__ import annotations

from pathlib import Path

import pytest

from suiyin_flow.treesha import resolve_tree_sha


def test_AC_freshness_non_git_directory_raises_value_error(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="git rev-parse"):
        resolve_tree_sha(tmp_path)
