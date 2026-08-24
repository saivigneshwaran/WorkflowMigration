#!/usr/bin/env sh
set -eu

repo_url="https://github.com/saivigneshwaran/WorkflowMigration.git"
target="WorkflowMigration"
branch="main"

usage() {
  cat <<'EOF'
Usage: scripts/sync_repo.sh [options]

Clone the WorkflowMigration repository, or pull an update in place if the
bundled Upgrade CLI already exists at the target.

Options:
  --repo-url <url>   Git URL to clone from. Default: https://github.com/saivigneshwaran/WorkflowMigration.git
  --target <path>    Destination directory. Default: WorkflowMigration
  --branch <name>    Branch to clone or pull. Default: main
  -h, --help         Show this help.
EOF
}

fail() {
  printf 'error: %s\n' "$*" >&2
  exit 2
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --repo-url)
      [ "$#" -ge 2 ] || fail "--repo-url requires a value"
      repo_url="$2"
      shift 2
      ;;
    --target)
      [ "$#" -ge 2 ] || fail "--target requires a value"
      target="$2"
      shift 2
      ;;
    --branch)
      [ "$#" -ge 2 ] || fail "--branch requires a value"
      branch="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      fail "unknown option: $1"
      ;;
  esac
done

upgrade_cli_path="$target/uipath-workflow-migrator/tools/uipath-upgrade-cli/UiPath.Upgrade.Cli"

if [ -e "$upgrade_cli_path" ]; then
  [ -d "$target/.git" ] || fail "$target already contains the Upgrade CLI but is not a git checkout; remove it or choose a different --target"
  printf 'Upgrade CLI found at %s; fetching only the update.\n' "$upgrade_cli_path"
  git -C "$target" fetch origin "$branch"
  git -C "$target" pull --ff-only origin "$branch"
elif [ -e "$target" ]; then
  fail "$target already exists but does not contain the Upgrade CLI; remove it or choose a different --target"
else
  printf 'Upgrade CLI not found; cloning repository into %s.\n' "$target"
  git clone --branch "$branch" "$repo_url" "$target"
fi
