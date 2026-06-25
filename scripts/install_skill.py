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


def agents_skills_dir() -> Path:
    agents_home = os.environ.get("AGENTS_HOME")
    if agents_home:
        return Path(agents_home).expanduser() / "skills"
    return Path.home() / ".agents" / "skills"


def scoped_dir(scope: str, global_path: Path, local_path: Path) -> Path:
    return global_path if scope == "global" else local_path


def resolve_agent_targets(agent: str, scope: str, explicit_targets: list[str]) -> list[Path]:
    targets: list[Path] = []

    if agent in ("codex", "agents", "all"):
        targets.append(scoped_dir(scope, agents_skills_dir(), Path(".agents") / "skills"))
    if agent in ("cursor", "all"):
        targets.append(scoped_dir(scope, Path.home() / ".cursor" / "skills", Path(".cursor") / "skills"))
    if agent in ("copilot", "all"):
        targets.append(scoped_dir(scope, Path.home() / ".github" / "skills", Path(".github") / "skills"))
    if agent in ("gemini", "all"):
        targets.append(scoped_dir(scope, Path.home() / ".gemini" / "skills", Path(".gemini") / "skills"))
    if agent in ("opencode", "all"):
        targets.append(scoped_dir(scope, Path.home() / ".config" / "opencode" / "skills", Path(".opencode") / "skills"))
    if agent in ("autopilot", "all"):
        targets.append(scoped_dir(scope, Path.home() / ".autopilot" / "skills", Path(".autopilot") / "skills"))

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
        choices=("codex", "cursor", "copilot", "gemini", "opencode", "autopilot", "agents", "all", "none"),
        default="all",
        help="Built-in skill destination to install to. Use none with --target for custom paths.",
    )
    parser.add_argument(
        "--scope",
        choices=("global", "local"),
        default="global",
        help="Install under the user's home directory or the current project.",
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

    targets = resolve_agent_targets(args.agent, args.scope, args.target)
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
