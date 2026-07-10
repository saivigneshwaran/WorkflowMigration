# Workflow Migration

`uipath-workflow-migrator` is an AI coding-agent skill for migrating UiPath Studio projects from Legacy or Windows-Legacy to Windows by using the bundled UiPath Upgrade CLI.

Migration analysis and conversion must be performed on Windows. The bundled Upgrade CLI depends on Windows runtime components, so run the skill on the Windows machine where the UiPath project can be analyzed and upgraded.

## Prerequisites (Windows)

Before installing the skill, make sure the Windows machine has:

- A compatible AI coding agent that supports skills.
- Git, or another way to copy this repository onto the machine.
- Access to the UiPath project folder that contains `project.json`.
- The complete `uipath-workflow-migrator` folder, including `SKILL.md`, `references`, `scripts`, and `tools`.
- Windows PowerShell. Python is optional because the skill includes both PowerShell and Python helper paths.

## How to Install the Skill

1. Clone the repository on the Windows machine.

```powershell
git clone https://github.com/saivigneshwaran/WorkflowMigration.git
cd WorkflowMigration
```

2. Install the skill into the supported skill locations for the coding agents on that machine.

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\install_skill.ps1 -Agent all -Mode copy
```

3. To install for only one agent, replace `all` with the target agent name.

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\install_skill.ps1 -Agent codex -Mode copy
```

4. To install into a custom skills directory, provide the target directory.

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\install_skill.ps1 -Agent none -Target C:\Path\To\Skills -Mode copy
```

5. Start a new coding-agent session so the agent can discover the installed skill.

## How to Update the Skill

If the skill was installed with `-Mode copy`, update the repository checkout and reinstall with `-Force`.

```powershell
cd C:\Path\To\WorkflowMigration
git pull --ff-only origin main

powershell -ExecutionPolicy Bypass -File .\scripts\install_skill.ps1 -Agent all -Mode copy -Force
```

If the skill was installed for only one agent, use the same agent name that was used during installation.

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\install_skill.ps1 -Agent codex -Mode copy -Force
```

If the skill was installed into a custom skills directory, provide the same target directory again.

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\install_skill.ps1 -Agent none -Target C:\Path\To\Skills -Mode copy -Force
```

If the skill was installed with `-Mode symlink`, update the repository checkout and restart the coding-agent session.

```powershell
cd C:\Path\To\WorkflowMigration
git pull --ff-only origin main
```

After updating, start a new coding-agent session so the agent can reload the latest skill files.

## Prompt Example

Use the skill from a coding-agent session on Windows:

```text
$uipath-workflow-migrator Convert project located in 'C:\Path\To\UiPathProject' to Windows
```

The skill analyzes the project first, generates a migration report, and asks for approval before running the upgrade.

For a deeper explanation of the execution flow, reporting model, risk categories, and common questions, see [How the Workflow Migrator Skill Works](HOW_THE_SKILL_WORKS.md).

## Execution Paths

Use the PowerShell helper on Windows when Python is not installed.

```powershell
$env:SKILL_DIR = "C:\Path\To\WorkflowMigration\uipath-workflow-migrator"

powershell -ExecutionPolicy Bypass -File "$env:SKILL_DIR\scripts\run_uipath_upgrade_cli.ps1" `
  -ConsentGated `
  -ProjectPath "C:\Path\To\UiPathProject" `
  -OutputPath "C:\Path\To\UiPathProject_Upgraded" `
  -CliVerbose
```

After reviewing the report and approving migration, rerun with `-ApproveMigration`.

```powershell
powershell -ExecutionPolicy Bypass -File "$env:SKILL_DIR\scripts\run_uipath_upgrade_cli.ps1" `
  -ConsentGated `
  -ProjectPath "C:\Path\To\UiPathProject" `
  -OutputPath "C:\Path\To\UiPathProject_Upgraded" `
  -ApproveMigration `
  -CliVerbose
```

If Python is installed and preferred, use the Python helper.

```powershell
python "$env:SKILL_DIR\scripts\run_uipath_upgrade_cli.py" `
  --consent-gated `
  --project-path "C:\Path\To\UiPathProject" `
  --output-path "C:\Path\To\UiPathProject_Upgraded" `
  --verbose
```
