# How the Workflow Migrator Skill Works

This guide explains how the `uipath-workflow-migrator` skill works, what it does during a migration, and how to answer common questions about its behavior.

## Short Answer

The skill is an AI coding-agent workflow for migrating UiPath Studio projects from Windows-Legacy or Legacy compatibility to Windows. It uses the bundled UiPath Upgrade CLI as the migration engine, runs analysis before any upgrade, generates a risk-focused migration report, asks for explicit approval, and only then runs the upgrade into a separate output folder.

The skill does not rely on finding a local Studio installation. The required Upgrade CLI is bundled inside the skill under:

```text
uipath-workflow-migrator/tools/uipath-upgrade-cli/
```

## What the Skill Contains

The skill is self-contained in the `uipath-workflow-migrator` folder.

Key files:

| File or folder | Purpose |
|---|---|
| `SKILL.md` | Main instructions used by coding agents. |
| `scripts/run_uipath_upgrade_cli.ps1` | Windows PowerShell helper. Use this when Python is not installed. |
| `scripts/run_uipath_upgrade_cli.py` | Python helper. Same migration workflow for environments with Python. |
| `tools/uipath-upgrade-cli/` | Bundled UiPath Upgrade CLI and runtime files. |
| `references/reporting-guidelines.md` | Defines the expected migration report structure. |
| `references/uipath-upgrade-cli.md` | Documents CLI options, helper behavior, and execution details. |
| `references/migration-operations-knowledge.md` | Captured migration knowledge used during normal execution. |

## Execution Flow

The normal migration flow is:

1. Inspect the UiPath project folder.
2. Locate the bundled `UiPath.Upgrade.exe` or `UiPath.Upgrade.dll`.
3. Run `analyze` first.
4. Parse SARIF and inspect project/XAML files.
5. Generate a migration risk report.
6. Stop and ask the user for approval.
7. Run `upgrade` only after explicit approval.
8. Write the upgraded project to a separate output folder.
9. Re-analyze the upgraded output and continue remediation where safe.

The original project is not upgraded during the analysis phase.

## Why Analysis Runs First

The skill is designed to avoid blind conversion. The first run is read-only from a migration perspective:

```powershell
powershell -ExecutionPolicy Bypass -File "$env:SKILL_DIR\scripts\run_uipath_upgrade_cli.ps1" `
  -ConsentGated `
  -ProjectPath "C:\Path\To\UiPathProject" `
  -OutputPath "C:\Path\To\UiPathProject_Upgraded" `
  -TargetStudioVersion "2025.10" `
  -CliVerbose
```

This produces a report and pauses. The user must review the report before approving the upgrade.

After approval:

```powershell
powershell -ExecutionPolicy Bypass -File "$env:SKILL_DIR\scripts\run_uipath_upgrade_cli.ps1" `
  -ConsentGated `
  -ProjectPath "C:\Path\To\UiPathProject" `
  -OutputPath "C:\Path\To\UiPathProject_Upgraded" `
  -TargetStudioVersion "2025.10" `
  -ApproveMigration `
  -CliVerbose
```

## Python Is Optional

Python is not mandatory on Windows. The recommended Windows path is the PowerShell helper:

```text
scripts/run_uipath_upgrade_cli.ps1
```

The Python helper remains available for environments where Python is already installed:

```text
scripts/run_uipath_upgrade_cli.py
```

Both helpers use the bundled UiPath Upgrade CLI.

## How the Risk Report Works

The report is assessment-oriented, not just a raw analyzer log. It combines:

- UiPath Upgrade CLI SARIF findings.
- `project.json` dependency inspection.
- XAML inspection for known migration-risk patterns.
- Captured migration knowledge from the skill references.

The report focuses on:

- overall migration status,
- package-version and target Studio compatibility,
- blockers,
- high-risk areas,
- medium-risk areas,
- exact evidence and locations where possible,
- owner,
- automation eligibility,
- remediation steps,
- validation expectations.

Raw analyzer output and the Migration Gate section are excluded by default. They can be included only when explicitly requested:

```powershell
-IncludeRawAnalyzerOutput -IncludeMigrationGate
```

## How Risks Are Categorized

The skill uses three practical severity levels.

| Severity | Meaning | Examples |
|---|---|---|
| `Blocker` | Migration should not proceed until resolved. | Missing packages, missing activity types, ambiguous VB `{}` expressions, unsupported `SaveImage`. |
| `High` | Migration can proceed only with careful review and validation. | Classic UI Automation, image/OCR activities, GSuite/Microsoft 365 connection changes, SOAP/web-service usage. |
| `Medium` | Runtime/configuration risk that needs cleanup or validation. | SMTP settings, hardcoded paths, URLs, emails, IDs, key paths. |

Overall status is derived from the highest severity:

| Condition | Status |
|---|---|
| Any blocker | `Blocked` |
| No blockers, but any high-risk item | `High Risk` |
| No high-risk items, but any medium-risk item | `Ready With Warnings` |
| No significant findings | `Ready` |

## Missing Dependencies Behavior

If the first analysis is blocked by missing packages, the helper runs a second discovery pass with:

```text
--ignore-missing-dependencies
```

This second pass is only used to uncover deeper migration risks. It does not make missing dependencies safe to ignore for upgrade. Missing packages or unresolved custom libraries remain blockers until resolved.

## How Package Versions Are Selected

The skill does not choose arbitrary package versions on its own. Package selection is controlled by the UiPath Upgrade CLI, its migration extensions, configured package feeds, and any explicit CLI options.

For general dependencies, UiPath guidance says conversion keeps the same package version when it exists in configured package sources. If that exact version is not available, the dependency is changed to the highest patch of the nearest available version. If no compatible version is available, the package remains a blocker.

The helper accepts the Studio version that will validate the converted project:

```powershell
-TargetStudioVersion "2025.10"
```

For Python:

```bash
--target-studio-version "2025.10"
```

This value is included in the report so users know where compatibility must be validated. It does not override package resolution by itself.

For supported Mail/Microsoft 365 migration, the bundled CLI exposes:

```text
--outlook-package-version
```

Use that option only when the target Studio environment requires a specific approved Microsoft Office 365 activities package version. Otherwise, validate the version selected by the CLI in the target Studio release.

For latest STS, do not rely on STS to create or edit the original Windows-Legacy source project. Convert through a compatible path, then validate the converted Windows project in STS.

## What the Skill Can Automate

The skill can automate or assist with:

- running the UiPath Upgrade CLI,
- generating analysis reports,
- classifying migration risks,
- identifying XAML locations and package issues,
- running upgrade after approval,
- re-analyzing the upgraded output,
- applying deterministic safe remediation in the Python helper path,
- guiding coding-agent remediation after upgrade.

## What Still Requires Human or Client Input

Some migration work cannot be safely automated without business or environment context.

Common examples:

- providing custom activity package source or feed access,
- confirming Windows-compatible versions of custom libraries,
- provisioning Orchestrator, GSuite, Microsoft 365, or SMTP connections,
- validating UI selectors against the real target application,
- confirming business behavior after migration,
- approving any change to original source project logic.

## Where the Upgrade Output Goes

The upgrade writes to the requested output folder:

```text
C:\Path\To\UiPathProject_Upgraded
```

If no output path is supplied, the default is:

```text
<project>_Upgraded
```

The original project should be preserved unless the user explicitly approves a change to it.

## Why the Skill Must Run on Windows

The bundled UiPath Upgrade CLI targets Windows runtime components. Analysis and upgrade should be performed on a Windows machine with access to:

- the UiPath project,
- package feeds,
- required dependencies,
- the bundled Upgrade CLI,
- the required .NET runtime.

## How Users Install or Update the Skill

Install:

```powershell
git clone https://github.com/saivigneshwaran/WorkflowMigration.git
cd WorkflowMigration
powershell -ExecutionPolicy Bypass -File .\scripts\install_skill.ps1 -Agent all -Mode copy
```

Update an existing copy-mode install:

```powershell
cd C:\Path\To\WorkflowMigration
git pull --ff-only origin main
powershell -ExecutionPolicy Bypass -File .\scripts\install_skill.ps1 -Agent all -Mode copy -Force
```

Restart the coding-agent session after install or update.

## Common Questions

### Does the skill modify the project immediately?

No. It analyzes first, writes a report, and stops. Upgrade requires explicit approval.

### Does it require Python?

No. On Windows, use the PowerShell helper. Python is optional.

### Does it require Studio to be installed?

The skill does not search for Studio as its normal execution path. It uses the bundled UiPath Upgrade CLI under `tools/uipath-upgrade-cli/`.

### Why does it generate a report before upgrading?

The report helps users understand blockers, risks, ownership, remediation steps, and validation requirements before making changes.

### Can it fully automate every migration?

No. It automates the safe tooling workflow and identifies risks, but custom libraries, credentials, connections, selectors, and business validation often require human or client input.

### What should users do after migration?

Open/build the upgraded project in Studio, review generated changes, validate dependencies, test selectors and connections, and run representative business tests.

## Suggested Explanation

Use this summary when explaining the skill:

> The Workflow Migrator skill wraps the UiPath Upgrade CLI in a safe, consent-gated process. It runs analysis first, enriches the analyzer findings with project and XAML risk checks, produces a practical migration risk report, and pauses for approval. Only after approval does it run the upgrade into a separate output folder. The skill supports a no-Python Windows path through PowerShell and keeps the Upgrade CLI bundled so it does not depend on discovering a Studio installation.
