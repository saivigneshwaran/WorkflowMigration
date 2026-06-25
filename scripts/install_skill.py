#!/usr/bin/env python3
"""Install the Workflow Migrator skill into common coding-agent skill folders."""

from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path


SKILL_NAME = "uipath-workflow-migrator"


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def codex_skills_dir() -> Path:
    codex_home = os.environ.get("CODEX_HOME")
    if codex_home:
        return Path(codex_home).expanduser() / "skills"
    return Path.home() / ".codex" / "skills"


def agents_skills_dir() -> Path:
    agents_home = os.environ.get("AGENTS_HOME")
    if agents_home:
        return Path(agents_home).expanduser() / "skills"
    return Path.home() / ".agents" / "skills"


def resolve_targets(agent: str, explicit_targets: list[str]) -> list[Path]:
    targets: list[Path] = []
    if agent in ("codex", "all"):
        targets.append(codex_skills_dir())
    if agent in ("agents", "all"):
        targets.append(agents_skills_dir())
    targets.extend(Path(target).expanduser() for target in explicit_targets)

    deduped: list[Path] = []
    seen: set[Path] = set()
    for target in targets:
        resolved = target.resolve() if target.exists() else target.absolute()
        if resolved not in seen:
            deduped.append(target)
            seen.add(resolved)
    return deduped


def remove_existing(path: Path) -> None:
    if path.is_symlink() or path.is_file():
        path.unlink()
    elif path.exists():
        shutil.rmtree(path)


def install_copy(source: Path, destination: Path, force: bool, dry_run: bool) -> None:
    if destination.exists() or destination.is_symlink():
        if not force:
            raise FileExistsError(f"{destination} already exists; use --force to replace it")
        if dry_run:
            print(f"would replace {destination}")
        else:
            remove_existing(destination)

    if dry_run:
        print(f"would copy {source} -> {destination}")
        return

    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, destination)


def install_symlink(source: Path, destination: Path, force: bool, dry_run: bool) -> None:
    if destination.exists() or destination.is_symlink():
        if not force:
            raise FileExistsError(f"{destination} already exists; use --force to replace it")
        if dry_run:
            print(f"would replace {destination}")
        else:
            remove_existing(destination)

    if dry_run:
        print(f"would symlink {destination} -> {source}")
        return

    destination.parent.mkdir(parents=True, exist_ok=True)
    relative_source = os.path.relpath(source, destination.parent)
    destination.symlink_to(relative_source, target_is_directory=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Install uipath-workflow-migrator into common coding-agent skill folders."
    )
    parser.add_argument(
        "--agent",
        choices=("codex", "agents", "all", "none"),
        default="all",
        help="Built-in skill destination to install to. Use none with --target for custom paths.",
    )
    parser.add_argument(
        "--target",
        action="append",
        default=[],
        help="Additional skills directory to install into. The skill folder is created inside it.",
    )
    parser.add_argument(
        "--mode",
        choices=("copy", "symlink"),
        default="copy",
        help="Copy is most portable; symlink avoids duplicating the bundled CLI.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Replace an existing installed skill folder or symlink.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print planned actions without changing files.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = repo_root()
    source = root / SKILL_NAME
    if not (source / "SKILL.md").is_file():
        print(f"error: missing skill source at {source}", file=sys.stderr)
        return 2

    targets = resolve_targets(args.agent, args.target)
    if not targets:
        print("error: no targets selected; pass --agent or --target", file=sys.stderr)
        return 2

    installer = install_copy if args.mode == "copy" else install_symlink
    for target_dir in targets:
        destination = target_dir / SKILL_NAME
        installer(source, destination, args.force, args.dry_run)
        print(f"installed {SKILL_NAME} at {destination}" if not args.dry_run else f"planned {destination}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
