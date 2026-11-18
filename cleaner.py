r"""
Delete all __pycache__ folders under E:\VS Code\Action\Action.

Skips: .venv312, .venv, venv, .git, data, node_modules

Usage:
    python cleaner.py
"""

import shutil
from pathlib import Path

ROOT = Path(r"E:\VS Code\Action\Action")

SKIP = {".venv312", ".venv", "venv", ".git", "data", "node_modules"}


def _skip(p: Path) -> bool:
    return any(part in SKIP for part in p.parts)


def main() -> None:
    targets = [
        p for p in ROOT.rglob("__pycache__")
        if p.is_dir() and not _skip(p)
    ]

    if not targets:
        print(f"[ok] No __pycache__ folders in {ROOT}")
        return

    print(f"Project: {ROOT}\n")

    deleted = 0
    for folder in sorted(targets):
        rel = folder.relative_to(ROOT)
        try:
            shutil.rmtree(folder)
            print(f"  deleted  {rel}")
            deleted += 1
        except OSError as e:
            print(f"  ! FAILED {rel}  ({type(e).__name__}: {e})")

    print(f"\nDone. Deleted {deleted}/{len(targets)} folder(s).")


if __name__ == "__main__":
    main()