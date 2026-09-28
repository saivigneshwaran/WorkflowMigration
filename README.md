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

## Installing the Skill

Find the section below for your coding agent and follow its steps in order. Every path installs from the same repository; only the last step or two differ.

### Claude Code

1. Add this repository as a plugin marketplace:
   ```powershell
   claude plugin marketplace add "https://github.com/saivigneshwaran/WorkflowMigration"
   ```
2. Install the plugin from it:
   ```powershell
   claude plugin install "uipath-workflow-migrator@workflow-migration-marketplace"
   ```
3. Restart the Claude Code session (plugins load at startup, so a running session won't see it yet).
4. Confirm it loaded:
   ```powershell
   claude plugin details "uipath-workflow-migrator@workflow-migration-marketplace"
   ```
   It should report `Skills (1)  uipath-workflow-migrator`.

> Installing from a local clone instead of GitHub works the same way — in step 1, use the clone's folder path instead of the URL, e.g. `claude plugin marketplace add "C:\Path\To\WorkflowMigration"`.

### Codex, Cursor, Copilot, Gemini, OpenCode, or Autopilot

1. Clone the repository:
   ```powershell
   git clone https://github.com/saivigneshwaran/WorkflowMigration.git
   cd WorkflowMigration
   ```
2. Install the skill for your agent. Replace `codex` with `cursor`, `copilot`, `gemini`, `opencode`, or `autopilot` to match the agent you use:
   ```powershell
   powershell -ExecutionPolicy Bypass -File .\scripts\install_skill.ps1 -Agent codex -Mode copy
   ```
3. Restart your coding-agent session so it discovers the installed skill.

> To install for every agent above in one go instead of just one, use `-Agent all` in step 2.

## Updating the Skill

Same idea as installing: refresh the repository first, then repeat the install step you used, with a couple of small differences noted below.

### Claude Code

1. If you installed from a **local clone**, refresh it:
   ```powershell
   powershell -ExecutionPolicy Bypass -File C:\Path\To\WorkflowMigration\scripts\sync_repo.ps1 -Target C:\Path\To\WorkflowMigration
   ```
   Claude Code reads the plugin straight from that folder, so this alone is enough — skip to step 3.
2. If you installed from the **GitHub URL** instead, update the marketplace and the plugin:
   ```powershell
   claude plugin marketplace update workflow-migration-marketplace
   claude plugin update "uipath-workflow-migrator@workflow-migration-marketplace"
   ```
3. Restart the Claude Code session.

### Codex, Cursor, Copilot, Gemini, OpenCode, or Autopilot

1. Refresh the repository:
   ```powershell
   powershell -ExecutionPolicy Bypass -File C:\Path\To\WorkflowMigration\scripts\sync_repo.ps1 -Target C:\Path\To\WorkflowMigration
   ```
2. If you installed with `-Mode copy`, reinstall with the same `-Agent` value you used originally, plus `-Force`:
   ```powershell
   powershell -ExecutionPolicy Bypass -File C:\Path\To\WorkflowMigration\scripts\install_skill.ps1 -Agent codex -Mode copy -Force
   ```
   If you installed with `-Mode symlink`, skip this step — step 1 already updated the skill in place.
3. Restart your coding-agent session.

## Prompt Example

Use the skill from a coding-agent session on Windows. Most agents pick it up from a natural-language mention:

```text
$uipath-workflow-migrator Convert project located in 'C:\Path\To\UiPathProject' to Windows
```

In Claude Code, invoke it as a slash command instead:

```text
/uipath-workflow-migrator Convert project located in 'C:\Path\To\UiPathProject' to Windows
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
  -TargetStudioVersion "2025.10" `
  -CliVerbose
```

After reviewing the report and approving migration, rerun with `-ApproveMigration`.

```powershell
powershell -ExecutionPolicy Bypass -File "$env:SKILL_DIR\scripts\run_uipath_upgrade_cli.ps1" `
  -ConsentGated `
  -ProjectPath "C:\Path\To\UiPathProject" `
  -OutputPath "C:\Path\To\UiPathProject_Upgraded" `
  -TargetStudioVersion "2025.10" `
  -ApproveMigration `
  -CliVerbose
```

If Python is installed and preferred, use the Python helper.

```powershell
python "$env:SKILL_DIR\scripts\run_uipath_upgrade_cli.py" `
  --consent-gated `
  --project-path "C:\Path\To\UiPathProject" `
  --output-path "C:\Path\To\UiPathProject_Upgraded" `
  --target-studio-version "2025.10" `
  --verbose
```

Use the Studio version that will open and validate the converted Windows project, such as `2024.10`, `2025.10`, or `latest STS`.
