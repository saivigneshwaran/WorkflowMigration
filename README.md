# Workflow Migration

This repository contains `uipath-workflow-migrator`, a Codex skill for migrating UiPath Studio projects with the bundled UiPath Upgrade CLI.

The skill is intended to be copied to another machine and run without needing to locate a Studio installation folder. The required upgrade CLI is included under the skill support files.

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
```

Key files:

- `uipath-workflow-migrator/SKILL.md` contains the skill instructions.
- `uipath-workflow-migrator/scripts/run_uipath_upgrade_cli.py` is the wrapper used to locate and run the bundled upgrade CLI.
- `uipath-workflow-migrator/references/migration-operations-knowledge.md` contains source-neutral migration knowledge used during analysis and remediation.
- `uipath-workflow-migrator/tools/uipath-upgrade-cli/UiPath.Upgrade.Cli/` contains the bundled Upgrade CLI folder.

## Installation

Clone this repository on the target machine, then copy the skill folder into the Codex skills directory:

```bash
mkdir -p "${CODEX_HOME:-$HOME/.codex}/skills"
cp -R uipath-workflow-migrator "${CODEX_HOME:-$HOME/.codex}/skills/"
```

The bundled CLI is intentionally stored as an extracted folder, not as a zip file. The skill can execute the CLI directly from `tools/uipath-upgrade-cli/UiPath.Upgrade.Cli/`.

## Usage

Set a helper variable for the installed skill:

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
