---
name: uipath-workflow-migrator
description: UiPath Workflow Migrator for bundled UiPath.Upgrade.Cli Studio project migration. Use when an agent needs to analyze or migrate UiPath project.json/.xaml projects from Windows-Legacy/Legacy to Windows, convert supported Classic activities to Modern activities, run Workflow Migrator/UiPath.Upgrade.exe analyze or upgrade commands, generate migration reports, obtain explicit user consent before migration, configure migration extensions, inspect SARIF/HTML reports, use captured migration operations knowledge, reduce status polling, attempt post-migration remediation, or assess Windows to Cross-platform/Portable migration support.
---

# UiPath Workflow Migrator

## Core Rule

Use the bundled `UiPath.Upgrade.Cli` as the source of truth. Do not hand-edit `project.json` or XAML as the primary migration path unless the user explicitly asks for a source-code implementation change or the CLI has no supported path and you explain the gap.

Always use this order:

1. Inspect the project and requested migration mode.
2. Load durable migration operations knowledge from [references/migration-operations-knowledge.md](references/migration-operations-knowledge.md).
3. Run `analyze` first.
4. Generate and present an analysis report.
5. Ask for explicit user consent before migration.
6. Run `upgrade` to a separate output folder only after consent.
7. Re-analyze the migrated output and automatically apply safe remediation before reporting unresolved items.

Never run `upgrade`, `bulk --command upgrade`, or any migration that writes files until the user has reviewed the analysis report and explicitly approved proceeding.

Read [references/uipath-upgrade-cli.md](references/uipath-upgrade-cli.md) when you need command options, source paths, extension names, runtime status behavior, or pipeline details. Read [references/post-migration-remediation.md](references/post-migration-remediation.md) before applying nontrivial fixes after upgrade. Read [references/windows-to-cross-platform.md](references/windows-to-cross-platform.md) before promising or implementing Windows to Cross-platform migration.

## Operational Knowledge

Migration operations knowledge is stored in [references/migration-operations-knowledge.md](references/migration-operations-knowledge.md). Treat that file as part of the skill's built-in knowledge base and use it during normal migrations without querying external systems.

If the user explicitly provides a new migration knowledge source and asks to refresh the skill, ingest it once, synthesize only durable issue/resolution guidance, update the reference file, and then return to offline operation. Do not store secrets, customer-sensitive payloads, access tokens, or raw personal data in the knowledge base.

## Portable Setup

When invoking the bundled helper, set `SKILL_DIR` to the folder that contains this `SKILL.md`. In a repository checkout, use:

```bash
SKILL_DIR="$PWD/uipath-workflow-migrator"
```

If the skill is installed into a Codex skills directory, use:

```bash
SKILL_DIR="${CODEX_HOME:-$HOME/.codex}/skills/uipath-workflow-migrator"
```

If another coding agent installs the skill into its own skill/plugin directory, set `SKILL_DIR` to that installed skill folder. Do not hard-code user-specific paths.

The Workflow Migrator CLI must be shipped with the skill under:

```text
tools/uipath-upgrade-cli/
```

That folder should contain the published `UiPath.Upgrade.exe` or `UiPath.Upgrade.dll` plus its runtime files, dependencies, `appsettings.json`, and `Extensions/` folder. Treat the original Studio source checkout as historical reference only; do not locate, build from, or require a Studio installation/source folder during normal skill execution.

## Migration Modes

Use the consent-gated workflow for single-project migration. The first run analyzes the project, writes a Markdown report, and stops:

```bash
python3 "$SKILL_DIR/scripts/run_uipath_upgrade_cli.py" \
  --consent-gated \
  --project-path /path/to/project \
  --output-path /path/to/project_Upgraded \
  --verbose
```

The helper waits for the CLI process to finish by default. Do not add tight status polling around it. If the caller needs progress messages, use coarse polling:

```bash
--status-mode poll --poll-interval-seconds 60
```

Present the generated report to the user. If the user approves, rerun with `--approve-migration`:

```bash
python3 "$SKILL_DIR/scripts/run_uipath_upgrade_cli.py" \
  --consent-gated \
  --project-path /path/to/project \
  --output-path /path/to/project_Upgraded \
  --approve-migration \
  --verbose
```

After an approved upgrade, the helper re-analyzes the output project, applies deterministic safe remediations, and writes `.upgrade/post-migration-remediation-report.md`. Continue with agent-driven fixes for remaining report findings instead of only suggesting next steps, but ask before touching the original source project or changing business logic.

For Classic to Modern activity conversion, keep extensions enabled. To be explicit, pass:

```bash
--enabled-extensions UiAutomationActivities,MailActivities,MicrosoftActivitiesExtension
```

For a repo/folder with multiple projects:

```bash
python3 "$SKILL_DIR/scripts/run_uipath_upgrade_cli.py" \
  -- bulk --command analyze --path /path/to/repository --verbose
```

Do not run `bulk --command upgrade` until the user has reviewed the bulk analysis report and explicitly approved the migration.

For direct CLI access, pass raw `UiPath.Upgrade.exe` arguments after `--`.

## Source-Aware Guidance

The checked source has these behaviors:

- Legacy/Windows-Legacy to Windows is implemented by `ProjectFrameworkUpdaterStep`.
- Classic activity migrations are extension-driven; the built-in extension names are `UiAutomationActivities`, `MailActivities`, and `MicrosoftActivitiesExtension`.
- `upgrade` writes to `--output-path`, or `<project>_Upgraded` when no output path is supplied.
- The current checked source does not implement a generic Windows to Cross-platform/Portable framework update. Treat that as unsupported until verified in the target branch or implemented.

## Build and Runtime Constraints

The CLI target is `net8.0-windows` and uses WPF/WindowsDesktop dependencies. Run it on Windows with the required .NET runtime and package/feed access. On macOS/Linux, use this skill for source inspection, command preparation, and report parsing unless a compatible prebuilt CLI is provided.

The helper script locates the bundled CLI and fails clearly if it is missing:

```bash
python3 "$SKILL_DIR/scripts/run_uipath_upgrade_cli.py" \
  --locate
```

## Validation

After migration:

1. Inspect `.upgrade` SARIF/HTML reports and the post-migration remediation report.
2. Verify `project.json` target framework and dependency changes in the output project.
3. Inspect changed `.xaml` files for unresolved namespaces/types.
4. Apply safe fixes in the output project and rerun analysis/build until findings are resolved or blocked.
5. Open/build the output project with Studio or supported automation when available.
6. Report only the unsupported or ambiguous items that remain after attempted remediation.
