#!/usr/bin/env sh
set -eu

skill_name="uipath-workflow-migrator"
agent="all"
scope="global"
mode="copy"
force=0
dry_run=0
targets=""

usage() {
  cat <<'EOF'
Usage: scripts/install_skill.sh [options]

Install uipath-workflow-migrator into common coding-agent skill folders.

Options:
  --agent <name>       codex, cursor, copilot, gemini, opencode, autopilot,
                       agents, all, or none. Default: all.
  --scope <scope>      global or local. Default: global.
  --target <path>      Additional skills directory to install into.
  --mode <mode>        copy or symlink. Default: copy.
  --force              Replace an existing installed skill folder or symlink.
  --dry-run            Print planned actions without changing files.
  -h, --help           Show this help.
EOF
}

fail() {
  printf 'error: %s\n' "$*" >&2
  exit 2
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --agent)
      [ "$#" -ge 2 ] || fail "--agent requires a value"
      agent="$2"
      shift 2
      ;;
    --scope)
      [ "$#" -ge 2 ] || fail "--scope requires a value"
      scope="$2"
      shift 2
      ;;
    --target)
      [ "$#" -ge 2 ] || fail "--target requires a value"
      targets="${targets}
$2"
      shift 2
      ;;
    --mode)
      [ "$#" -ge 2 ] || fail "--mode requires a value"
      mode="$2"
      shift 2
      ;;
    --force)
      force=1
      shift
      ;;
    --dry-run)
      dry_run=1
      shift
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

case "$agent" in
  codex|cursor|copilot|gemini|opencode|autopilot|agents|all|none) ;;
  *) fail "unsupported agent: $agent" ;;
esac

case "$scope" in
  global|local) ;;
  *) fail "unsupported scope: $scope" ;;
esac

case "$mode" in
  copy|symlink) ;;
  *) fail "unsupported mode: $mode" ;;
esac

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
repo_root=$(CDPATH= cd -- "$script_dir/.." && pwd)
source_dir="$repo_root/$skill_name"

[ -f "$source_dir/SKILL.md" ] || fail "missing skill source at $source_dir"

home_dir=${HOME:-}
[ -n "$home_dir" ] || fail "HOME is not set"

target_list=""

add_target() {
  target_list="${target_list}
$1"
}

scoped_target() {
  global_path="$1"
  local_path="$2"
  if [ "$scope" = "global" ]; then
    printf '%s\n' "$global_path"
  else
    printf '%s\n' "$local_path"
  fi
}

if [ "$agent" = "codex" ] || [ "$agent" = "agents" ] || [ "$agent" = "all" ]; then
  agents_home=${AGENTS_HOME:-"$home_dir/.agents"}
  add_target "$(scoped_target "$agents_home/skills" ".agents/skills")"
fi

if [ "$agent" = "cursor" ] || [ "$agent" = "all" ]; then
  add_target "$(scoped_target "$home_dir/.cursor/skills" ".cursor/skills")"
fi

if [ "$agent" = "copilot" ] || [ "$agent" = "all" ]; then
  add_target "$(scoped_target "$home_dir/.github/skills" ".github/skills")"
fi

if [ "$agent" = "gemini" ] || [ "$agent" = "all" ]; then
  add_target "$(scoped_target "$home_dir/.gemini/skills" ".gemini/skills")"
fi

if [ "$agent" = "opencode" ] || [ "$agent" = "all" ]; then
  add_target "$(scoped_target "$home_dir/.config/opencode/skills" ".opencode/skills")"
fi

if [ "$agent" = "autopilot" ] || [ "$agent" = "all" ]; then
  add_target "$(scoped_target "$home_dir/.autopilot/skills" ".autopilot/skills")"
fi

if [ -n "$targets" ]; then
  target_list="${target_list}${targets}"
fi

has_target=0
while IFS= read -r target_dir; do
  [ -n "$target_dir" ] || continue
  has_target=1
  destination="$target_dir/$skill_name"

  if [ -e "$destination" ] || [ -L "$destination" ]; then
    if [ "$force" -ne 1 ]; then
      fail "$destination already exists; pass --force to replace it"
    fi
    if [ "$dry_run" -eq 1 ]; then
      printf 'would replace %s\n' "$destination"
    else
      rm -rf -- "$destination"
    fi
  fi

  if [ "$dry_run" -eq 1 ]; then
    if [ "$mode" = "copy" ]; then
      printf 'would copy %s -> %s\n' "$source_dir" "$destination"
    else
      printf 'would symlink %s -> %s\n' "$destination" "$source_dir"
    fi
    printf 'planned %s\n' "$destination"
    continue
  fi

  mkdir -p -- "$target_dir"
  if [ "$mode" = "copy" ]; then
    cp -R -- "$source_dir" "$destination"
  else
    ln -s -- "$source_dir" "$destination"
  fi
  printf 'installed %s at %s\n' "$skill_name" "$destination"
done <<EOF
$target_list
EOF

if [ "$has_target" -eq 0 ]; then
  fail "no targets selected; pass --agent or --target"
fi
