from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]


def repo_path(*parts: str) -> Path:
    return REPO_ROOT.joinpath(*parts)


def add_repo_path(*parts: str) -> Path:
    path = repo_path(*parts)
    path_text = str(path)
    if path_text not in sys.path:
        sys.path.insert(0, path_text)
    return path
