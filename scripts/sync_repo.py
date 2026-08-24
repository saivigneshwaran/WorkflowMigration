#!/usr/bin/env python3
"""Clone WorkflowMigration, or pull an update in place if the Upgrade CLI already exists."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

DEFAULT_REPO_URL = "https://github.com/saivigneshwaran/WorkflowMigration.git"
UPGRADE_CLI_RELATIVE = Path("uipath-workflow-migrator") / "tools" / "uipath-upgrade-cli" / "UiPath.Upgrade.Cli"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Clone WorkflowMigration, or pull an update if the Upgrade CLI is already present."
    )
    parser.add_argument("--repo-url", default=DEFAULT_REPO_URL, help="Git URL to clone from.")
    parser.add_argument("--target", default="WorkflowMigration", help="Destination directory.")
    parser.add_argument("--branch", default="main", help="Branch to clone or pull.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    target = Path(args.target).expanduser().resolve()
    upgrade_cli_path = target / UPGRADE_CLI_RELATIVE

    if upgrade_cli_path.exists():
        if not (target / ".git").exists():
            print(
                f"error: {target} already contains the Upgrade CLI but is not a git checkout; "
                "remove it or choose a different --target",
                file=sys.stderr,
            )
            return 2

        print(f"Upgrade CLI found at {upgrade_cli_path}; fetching only the update.")
        subprocess.run(["git", "fetch", "origin", args.branch], cwd=target, check=True)
        subprocess.run(["git", "pull", "--ff-only", "origin", args.branch], cwd=target, check=True)
        return 0

    if target.exists():
        print(
            f"error: {target} already exists but does not contain the Upgrade CLI; "
            "remove it or choose a different --target",
            file=sys.stderr,
        )
        return 2

    print(f"Upgrade CLI not found; cloning repository into {target}.")
    subprocess.run(["git", "clone", "--branch", args.branch, args.repo_url, str(target)], check=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
