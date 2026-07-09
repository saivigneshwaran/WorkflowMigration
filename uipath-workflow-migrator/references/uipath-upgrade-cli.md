# UiPath.Upgrade.Cli Reference

## Bundled Tool Layout

Normal skill execution uses a bundled CLI, not a Studio source checkout. Place the published Workflow Migrator CLI under:

```text
tools/uipath-upgrade-cli/
```

Expected contents include `UiPath.Upgrade.exe` or `UiPath.Upgrade.dll`, runtime/dependency files, `appsettings.json`, and the `Extensions/` folder. The helper script searches this folder recursively and can also use `--cli` or `UIPATH_UPGRADE_CLI` for an explicit CLI path.

## Historical Source Map

These paths came from the one-time Studio source reference and are retained only for implementation context:

- CLI project: `Upgrade/UiPath.Upgrade.Cli/UiPath.Upgrade.Cli.csproj`
- Bootstrapper: `Upgrade/UiPath.Upgrade.Cli.Bootstrapper`
- Solution: `Upgrade/UiPath.Upgrade.sln`
- Expected published CLI output: `Upgrade/Output/cli/<Configuration>/UiPath.Upgrade.exe`
- Main entrypoint: `Upgrade/UiPath.Upgrade.Cli/Program.cs`
- Core options: `Upgrade/UiPath.Upgrade.Cli/Commands/GlobalOptions.cs`
- Project options: `Upgrade/UiPath.Upgrade.Cli/Commands/UpgradeCommandOptions.cs`
- Bulk command: `Upgrade/UiPath.Upgrade.Cli/Commands/BulkCommand.cs`
- Pipeline order: `Upgrade/UiPath.Upgrade.Cli/StepOrchestrator.cs`
- Legacy to Windows update: `Upgrade/UiPath.Upgrade.Cli/Steps/ProjectFrameworkUpdaterStep.cs`
- Output copy/save: `Upgrade/UiPath.Upgrade.Cli/Steps/ProjectCopyStep.cs`

## Commands

Root command name is `UiPath.Upgrade.exe`.

- `analyze`: read-only project assessment; excludes `ProjectCopyStep`.
- `upgrade`: runs the migration pipeline and writes an output project.
- `bulk`: recursively finds UiPath projects under a folder and runs `analyze` or `upgrade`.
- `version`: custom version handling exists in the CLI program.

The skill includes two helper paths:

- `scripts/run_uipath_upgrade_cli.ps1`: Windows-native helper; prefer this path when Python is not installed.
- `scripts/run_uipath_upgrade_cli.py`: Python helper; use when Python is available or when maintaining Python-specific behavior.

The default helper workflow runs `analyze`, generates a Markdown report from the newest SARIF output, then stops unless approval is supplied after explicit user consent. Use `-ApproveMigration` with the PowerShell helper or `--approve-migration` with the Python helper.

The helper waits for analyze/upgrade subprocesses to finish by default. Do not wrap it in continuous status polling. If progress updates are required, use `--status-mode poll` with `--poll-interval-seconds` set to a coarse interval; the default interval is 60 seconds and values under 5 seconds are rejected.

After an approved upgrade, the helper runs a post-upgrade analysis against the output project, applies deterministic safe remediations, re-analyzes if it changed files, and writes `.upgrade/post-migration-remediation-report.md`. Pass `--skip-remediation` only when the caller will perform remediation separately.

Important options:

- `--project-path`, `-p`: required path to a UiPath project folder containing `project.json`.
- `--output-path`, `-o`: output project path. If omitted for `upgrade`, output defaults to `<project>_Upgraded`.
- `--verbose`, `-v`: verbose logging.
- `--output-format`, `-f`: `console` or `sarif`.
- `--extension-directory`, `-e`: extension directory. Default is `Extensions` beside the CLI executable.
- `--enabled-extensions`: comma-separated allowlist.
- `--disabled-extensions`: comma-separated denylist.
- `--disable-all-extensions`: disable extension-driven migrations.
- `--ignore-missing-dependencies`: continue with warnings when dependencies cannot be restored.
- Helper option `--status-mode wait|poll`: wait silently for process completion or print coarse status updates.
- Helper option `--poll-interval-seconds`: status update interval for `--status-mode poll`; defaults to 60 seconds.
- Helper option `--skip-remediation`: disables the default post-upgrade remediation pass.

PowerShell helper options use PowerShell casing, for example `-ConsentGated`, `-ProjectPath`, `-OutputPath`, `-ApproveMigration`, `-StatusMode poll`, `-PollIntervalSeconds 60`, `-IncludeRawAnalyzerOutput`, and `-IncludeMigrationGate`.

## Built-In Extensions

The checked source includes these extension names:

- `UiAutomationActivities`: registers UI Automation package upgrade and activity migration steps.
- `MailActivities`: migrates supported Outlook/Mail activities toward Microsoft 365 activities and reporting.
- `MicrosoftActivitiesExtension`: removes/replaces Microsoft activities package usage and namespaces.

Extensions are discovered from subdirectories under `Extensions`. Each extension directory must contain a matching main assembly named `UiPath.Upgrade.<ExtensionDirectoryName>.dll`.

## Pipeline

Known step order:

1. `ProjectLoadStep`
2. `ProjectFrameworkUpdaterStep`
3. `XamlParseStep`
4. `RestoreStep`
5. `LoadAssembliesStep`
6. `RepairLocalAssembliesStep`
7. `TypeCheckStep`
8. `ReferencesFixStep`
9. `LoadWorkflowsStep`
10. `ValidateWorkflowStep`
11. Extension workflow steps, ordered by attributes or after workflow loading
12. `ProjectCopyStep` for `upgrade` only

`ProjectFrameworkUpdaterStep` changes `TargetFramework.Legacy` to `TargetFramework.Windows`. `RestoreStep` currently uses Windows as the restore target. `ProjectCopyStep` copies files, excludes `.settings` and `.upgrade`, writes settings, saves transformed XAML, and saves `project.json`.

## Reporting

Migration artifacts are written to the project `.upgrade` folder. SARIF and HTML reports are generated by `SarifExporter`.

The helper's Markdown report is an assessment report, not a raw log. It classifies SARIF findings and XAML/project inspection into readiness, validation evidence, risk register, blockers, automated changes, owner/remediation guidance, final recommendation, and finding counts. Raw analyzer output and the migration gate section are excluded by default. Include them only when the user explicitly asks for them by passing `-IncludeRawAnalyzerOutput` / `-IncludeMigrationGate` in PowerShell or `--include-raw-analyzer-output` / `--include-migration-gate` in Python.

When a primary analyze run reports missing package/restore blockers, run a second analyze pass with `--ignore-missing-dependencies` unless the caller already supplied that option. Use the second SARIF only to uncover additional issues behind restore failures. Do not treat the ignored-dependencies run as approval to upgrade without resolving package and type-resolution blockers.

The assessment should include documented Windows migration risk patterns: custom or third-party libraries, productivity activity `ConnectionId` requirements for GSuite/Microsoft 365, UI Automation application scope/selector validation, SMTP/mail strategy, image/OCR activity fragility, hardcoded environment values, ambiguous VB expressions such as `{}` requiring typed replacements, and unsupported SOAP/web-service usage.
