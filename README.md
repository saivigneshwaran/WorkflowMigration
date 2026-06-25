# Workflow Migration

This repository contains `uipath-workflow-migrator`, an AI coding-agent skill for migrating UiPath Studio projects with the bundled UiPath Upgrade CLI.

The skill is intended to be copied to another machine or installed by a compatible coding agent without needing to locate a Studio installation folder. The required upgrade CLI is included under the skill support files.

## What It Does

- Analyzes the current UiPath project setup before making changes.
- Generates a migration analysis report for review.
- Requires explicit approval before running the upgrade.
- Migrates Legacy or Windows-Legacy projects to Windows by using the bundled `UiPath.Upgrade.Cli`.
- Converts supported Classic activities to Modern activities through the upgrade CLI extension flow.
- Uses captured migration knowledge for known package issues, common resolutions, and operational checks.
- Re-analyzes the migrated output and attempts safe automatic remediation for issues it can confidently fix.
- Waits for analysis and upgrade processes to finish by default, with optional coarse polling for status updates.

## Repository Layout

```text
uipath-workflow-migrator/
  SKILL.md
  references/
    migration-operations-knowledge.md
  scripts/
    run_uipath_upgrade_cli.py
  tools/
    uipath-upgrade-cli/
      UiPath.Upgrade.Cli/
.agents/
  skills -> ../skills
skills/
  uipath-workflow-migrator -> ../uipath-workflow-migrator
.claude-plugin/
.codex-plugin/
.gemini/
.cursor/
scripts/
  install_skill.py
```

Key files:

- `uipath-workflow-migrator/SKILL.md` contains the skill instructions.
- `skills/uipath-workflow-migrator` is a discovery alias for agents that scan a `skills/` directory.
- `.agents/skills` is a discovery alias for agents that scan `.agents/skills`.
- `AGENTS.md`, `CLAUDE.md`, and `GEMINI.md` provide shared root instructions for coding agents that read project-level context files.
- `uipath-workflow-migrator/scripts/run_uipath_upgrade_cli.py` is the wrapper used to locate and run the bundled upgrade CLI.
- `uipath-workflow-migrator/references/migration-operations-knowledge.md` contains source-neutral migration knowledge used during analysis and remediation.
- `uipath-workflow-migrator/tools/uipath-upgrade-cli/UiPath.Upgrade.Cli/` contains the bundled Upgrade CLI folder.
- `.claude-plugin/plugin.json`, `.codex-plugin/plugin.json`, `.gemini/settings.json`, and `.cursor/rules/` provide compatibility metadata for common coding-agent hosts.
- `scripts/install_skill.py` installs the canonical skill folder into common local skills directories.

## Agent Compatibility

The repository follows the UiPath skills repository pattern for multi-tool support:

- Claude-compatible plugin metadata points at `./skills/`.
- Codex-compatible plugin metadata points at `./skills/`.
- Gemini reads `GEMINI.md`, `AGENTS.md`, or `CLAUDE.md` as project context.
- Cursor reads repository rules from `.cursor/rules/`.
- Agents that scan `.agents/skills` can discover the same skill through the alias.

The canonical skill content remains in `uipath-workflow-migrator/`; aliases avoid duplicating the large bundled CLI.

## Installation

Clone this repository on the target machine. Compatible coding agents can use the repository-level metadata directly when installed as a plugin or opened as a skill repository.

Use the common installer when the agent expects skills to be present in a local skills directory:

```bash
python3 scripts/install_skill.py --agent all --mode copy
```

This installs the canonical skill folder into:

- Codex: `${CODEX_HOME:-$HOME/.codex}/skills/uipath-workflow-migrator`
- Agent-compatible skill root: `${AGENTS_HOME:-$HOME/.agents}/skills/uipath-workflow-migrator`

For a custom skills directory:

```bash
python3 scripts/install_skill.py --agent none --target /path/to/skills --mode copy
```

Use `--mode symlink` when the target machine will keep this repository checkout in place and you want to avoid duplicating the bundled CLI. Use `--force` to replace an existing install.

The bundled CLI is intentionally stored as an extracted folder, not as a zip file. The skill can execute the CLI directly from `tools/uipath-upgrade-cli/UiPath.Upgrade.Cli/`.

## Usage

Set a helper variable for the skill folder. From the repository root:

```bash
SKILL_DIR="$PWD/uipath-workflow-migrator"
```

For a direct Codex skill install:

```bash
SKILL_DIR="${CODEX_HOME:-$HOME/.codex}/skills/uipath-workflow-migrator"
```

Confirm the bundled CLI can be located:

```bash
python3 "$SKILL_DIR/scripts/run_uipath_upgrade_cli.py" --locate
```

Run analysis and generate the report:

```bash
python3 "$SKILL_DIR/scripts/run_uipath_upgrade_cli.py" \
  --consent-gated \
  --project-path /path/to/uipath-project \
  --output-path /path/to/uipath-project-upgraded \
  --verbose
```

The first consent-gated run stops after analysis and writes a report. Review the report, then approve the migration:

```bash
python3 "$SKILL_DIR/scripts/run_uipath_upgrade_cli.py" \
  --consent-gated \
  --project-path /path/to/uipath-project \
  --output-path /path/to/uipath-project-upgraded \
  --approve-migration \
  --verbose
```

Optional coarse polling can be enabled when periodic status messages are useful:

```bash
python3 "$SKILL_DIR/scripts/run_uipath_upgrade_cli.py" \
  --consent-gated \
  --project-path /path/to/uipath-project \
  --output-path /path/to/uipath-project-upgraded \
  --approve-migration \
  --status-mode poll \
  --poll-interval-seconds 60
```

## Reports

The wrapper writes reports into `.upgrade` folders:

- Analysis report: `<project>/.upgrade/migration-analysis-report.md`
- Post-migration remediation report: `<output>/.upgrade/post-migration-remediation-report.md`

## Runtime Notes

The bundled UiPath Upgrade CLI targets Windows runtime components. Run actual project analysis and upgrade operations on a Windows machine with the required .NET and Windows desktop runtime support available.

On non-Windows machines, the repository can still be inspected, copied, committed, and validated structurally, but the bundled upgrade executable is expected to run on Windows.

## Safety Model

- The skill analyzes first and requires explicit approval before upgrading.
- Upgrade output is written to the configured output folder.
- Automatic remediation is limited to safe, deterministic changes in the migrated output.
- Higher-risk fixes are reported for review instead of being applied silently.
