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

1. Get the repository onto the Windows machine. `scripts/sync_repo.ps1` checks the target directory first: if the bundled Upgrade CLI is already there it fetches only the update (`git pull --ff-only`) instead of downloading the entire repository again; otherwise it does a full `git clone`. On the very first run (nothing local yet), download the script once and run it:

```powershell
Invoke-WebRequest -Uri https://raw.githubusercontent.com/saivigneshwaran/WorkflowMigration/main/scripts/sync_repo.ps1 -OutFile sync_repo.ps1
.\sync_repo.ps1
cd WorkflowMigration
```

From then on, rerun the copy of the script inside the checkout (`.\WorkflowMigration\scripts\sync_repo.ps1`) to update in place — it will detect the existing Upgrade CLI and pull only the changes. Plain `git clone` still works if you prefer to manage the checkout yourself:

```powershell
git clone https://github.com/saivigneshwaran/WorkflowMigration.git
cd WorkflowMigration
```

2. Install the skill into the supported skill locations for the coding agents on that machine. This step covers Codex, Cursor, Copilot, Gemini, OpenCode, Autopilot, and any generic agent that reads from `~/.agents/skills`. **Claude Code installs differently — see the [Claude Code](#claude-code) section below.**

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\install_skill.ps1 -Agent all -Mode copy
```

3. To install for only one agent, replace `all` with the target agent name (`codex`, `cursor`, `copilot`, `gemini`, `opencode`, `autopilot`, or `agents`).

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\install_skill.ps1 -Agent codex -Mode copy
```

4. To install into a custom skills directory, provide the target directory.

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\install_skill.ps1 -Agent none -Target C:\Path\To\Skills -Mode copy
```

5. Start a new coding-agent session so the agent can discover the installed skill.

### Claude Code

Claude Code discovers this skill through its own plugin/marketplace mechanism instead of `install_skill.ps1`. From inside the cloned repository:

```powershell
claude plugin marketplace add "https://github.com/saivigneshwaran/WorkflowMigration"
claude plugin install "uipath-workflow-migrator@workflow-migration-marketplace"
```

If you already have a local clone and prefer to install straight from it instead of from GitHub, point `marketplace add` at the local folder:

```powershell
claude plugin marketplace add "C:\Path\To\WorkflowMigration"
claude plugin install "uipath-workflow-migrator@workflow-migration-marketplace"
```

Restart the Claude Code session afterward — plugins are loaded at session start, so a session already running when you install won't see the skill until it's restarted. Verify the skill loaded with:

```powershell
claude plugin details "uipath-workflow-migrator@workflow-migration-marketplace"
```

which should report `Skills (1)  uipath-workflow-migrator`.

## How to Update the Skill

If the skill was installed with `-Mode copy`, update the repository checkout and reinstall with `-Force`. `sync_repo.ps1` detects the existing Upgrade CLI and fetches only the update rather than re-cloning the repository.

```powershell
powershell -ExecutionPolicy Bypass -File C:\Path\To\WorkflowMigration\scripts\sync_repo.ps1 -Target C:\Path\To\WorkflowMigration

powershell -ExecutionPolicy Bypass -File C:\Path\To\WorkflowMigration\scripts\install_skill.ps1 -Agent all -Mode copy -Force
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
powershell -ExecutionPolicy Bypass -File C:\Path\To\WorkflowMigration\scripts\sync_repo.ps1 -Target C:\Path\To\WorkflowMigration
```

After updating, start a new coding-agent session so the agent can reload the latest skill files.

### Claude Code

If the marketplace was added from a local clone, updating that clone is enough — Claude Code reads the plugin straight from the folder, so just refresh it and restart the session:

```powershell
powershell -ExecutionPolicy Bypass -File C:\Path\To\WorkflowMigration\scripts\sync_repo.ps1 -Target C:\Path\To\WorkflowMigration
```

If the marketplace was added from the GitHub URL instead, refresh the marketplace and update the plugin explicitly:

```powershell
claude plugin marketplace update workflow-migration-marketplace
claude plugin update "uipath-workflow-migrator@workflow-migration-marketplace"
```

Restart the Claude Code session afterward to apply the update.

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
