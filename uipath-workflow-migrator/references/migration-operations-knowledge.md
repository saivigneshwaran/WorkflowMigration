# Migration Operations Knowledge

## Capture Policy

Use this file as the durable knowledge base for migration lessons learned.

When the user explicitly provides a new migration knowledge source and asks to refresh this skill:

1. Collect bounded migration-relevant material about UiPath migration, Upgrade CLI, Windows-Legacy, Windows, Cross-platform, Classic activities, Modern activities, package restore, XAML validation, and Studio build issues.
3. Synthesize the results into short issue/resolution entries below.
4. Keep only durable operational guidance.
5. Do not query external systems during normal migration execution unless the user explicitly asks for a refresh.

Do not persist secrets, customer data, tokens, personal data, or raw private conversations. Keep entries sanitized and operational.

## Knowledge Scope

- Captured: 2026-06-22.
- Scope: operational migration knowledge about package ownership, SharePoint custom activities, Microsoft.Activities, dependency conflicts, and marketplace source/package storage.
- Refresh only when the user explicitly asks for a new capture.

## Issue And Resolution Entries

### SharePoint custom activities package has a Windows migration path
- Applies to: `UiPathTeam.SharePoint.Activities`, SharePoint Custom Activities Package, Windows-Legacy to Windows.
- Symptoms: Windows migration is blocked or noisy when a project uses the old SharePoint custom activities package; old package versions use .NET Framework-era dependencies and may conflict with newer `UiPath.System.Activities`.
- Likely cause: the old package depends on legacy SharePoint libraries and older dependency ranges; the migrated package moved from the old CSOM/PnP-style implementation to SharePoint REST API for Windows compatibility.
- Automatic remediation: in migrated output projects, prefer `UiPathTeam.SharePoint.Activities` version `>= 2.0.0` when replacing old `1.x` package usage for Windows projects. Preserve existing workflow shape where the new package remains backward compatible. Do not downgrade `UiPath.System.Activities` to work around the old package unless the user explicitly requests that tradeoff.
- Manual fallback: read the Marketplace release notes and package guide before upgrade. Expect minor workflow/configuration changes and require non-production validation because the runtime/API changed.
- Validation: run the Workflow Migrator analysis, inspect SARIF, then run project validation/build and targeted SharePoint workflow tests against the customer's SharePoint Online or On-Prem environment.

### Newtonsoft.Json conflict with old SharePoint package
- Applies to: `UiPathTeam.SharePoint.Activities` `1.7.0`, `UiPath.System.Activities` `24.10`, disconnected proxy/cloud migration scenarios.
- Symptoms: dependency resolution warning or validation concern around `Newtonsoft.Json`; `UiPath.System.Activities` may require `Newtonsoft.Json` `13.0.3` while the old SharePoint package dependency range is older.
- Likely cause: old SharePoint package dependency chain includes archived SharePoint/PnP components and cannot receive a clean dependency update.
- Automatic remediation: if moving to Windows, upgrade the SharePoint package to the Windows package line `>= 2.0.0`, which uses newer dependencies. If remaining on Legacy, treat dependency resolution as a validation finding: do not automatically downgrade other core activities; run validation and workflow tests first.
- Manual fallback: when the project must temporarily remain Legacy, test affected workflows. If validation passes with a warning, document the accepted warning; if validation fails, the realistic options are package upgrade/migration or carefully selected dependency downgrades approved by the user.
- Validation: verify dependency restore, Studio validation, and representative SharePoint activity execution. Do not treat the warning alone as fatal if validation and tests pass.

### SharePoint authentication and API behavior require targeted validation
- Applies to: `UiPathTeam.SharePoint.Activities` Windows package, SharePoint Online, SharePoint Server 2016 On-Prem, SharePoint Server 2019 On-Prem.
- Symptoms: migrated workflows need authentication/configuration review; customers may ask about AppOnly, WebOnly, Azure App client credentials, or legacy sign-in retirement.
- Likely cause: the Windows package uses a different runtime and REST API path than the old package, and not every legacy authentication pattern maps to a modern recommended approach.
- Automatic remediation: preserve existing connection/authentication fields only when the package supports them and the workflow validates. Flag authentication-related findings as requiring environment-specific testing rather than blindly rewriting credentials or connection modes.
- Manual fallback: ask for the customer's SharePoint topology and authentication method. Prefer modern, secure authentication where available, but do not change credentials, app registrations, or endpoints without explicit approval.
- Validation: test in non-production against the same SharePoint type and auth mode. The channel noted successful broad testing for SharePoint Online, SharePoint Server 2016 On-Prem, and SharePoint Server 2019 On-Prem, while some legacy On-Prem auth modes still need customer-side verification.

### Microsoft.Activities replacement is not fully automatic
- Applies to: `Microsoft.Activities`, `Microsoft.Activities.Extensions`, Legacy to Windows and Classic to Modern migration.
- Symptoms: a migrated project depends on Microsoft marketplace activities that have no direct Windows-compatible equivalent, or requires replacing one activity with another activity/group of activities.
- Likely cause: Windows migration can update project/runtime/package compatibility, but activity-level semantic replacement is not guaranteed. Some replacements require understanding which exact activities are used and whether official package alternatives exist.
- Automatic remediation: before replacing anything, inventory XAML usage by namespace/package across the project or repository. Use this inventory to prioritize replacements and detect one-to-one mappings. Apply automatic replacements only when a documented equivalent exists and the behavior is unchanged.
- Manual fallback: ask the user for approval when replacement changes behavior, requires a group of activities, or has multiple possible official alternatives. Legacy projects may continue to run for a period without new features, so do not force risky replacements solely to eliminate all legacy usage.
- Validation: re-run analysis after each replacement and compare workflow behavior with representative test data.

### Use XAML inventory to plan package migration at scale
- Applies to: large customers or repositories with many UiPath projects/processes.
- Symptoms: the customer cannot manually list package/activity usage across hundreds of processes, making migration impact unclear.
- Likely cause: package usage lives in many XAML files and repositories; Marketplace packages may not have telemetry detailed enough to identify exact activities.
- Automatic remediation: scan XAML files in the available source tree for namespaces/types belonging to target packages, then produce a package/activity inventory before proposing replacements. Use repository-level scanning when projects are under source control.
- Manual fallback: ask the user for repository access or exported project folders if source control is not locally available.
- Validation: include counts by package, activity/type, workflow file, and project so package owners can prioritize migration work.

### Known marketplace packages already migrated by internal effort
- Applies to: marketplace package detection and remediation suggestions.
- Symptoms: a project references older marketplace packages where a newer Windows or Cross-platform package may already exist.
- Likely cause: several high-usage marketplace packages were migrated separately and their source/package artifacts may live in Marketplace, Jira, individual repositories, or an internal consolidated repo.
- Automatic remediation: when one of these packages appears, check whether a newer Windows-compatible package exists before proposing custom XAML rewrites:
  - `UiPathTeam.SharePoint.Activities`: Windows package line exists; public source noted at `https://github.com/UiPath-Services/UiPathTeam.SharePoint.Activities`.
  - Excel Extension Activities: Windows migration exists; ownership changed after migration.
  - Generate Random Password: Windows and Cross-platform migration exists.
  - Get Pixels from Image: Windows migration exists.
  - Activity for Google Sheets API: Windows and Cross-platform migration exists.
  - Attended Robot Status Window: Windows migration exists.
  - HTML to DataTable: Windows and Cross-platform migration exists.
  - Cron Expression: Windows and Cross-platform migration exists.
- Manual fallback: if source/package location is unclear, check Marketplace, Jira, the internal marketplace activities repository, or ask the package owner before hand-building replacements.
- Validation: update package versions in an output copy, restore dependencies, run analyzer, and validate representative workflows.

### Package ownership and migration strategy
- Applies to: deciding whether to migrate package usage, replace with official activities, or route to a product team.
- Symptoms: a package is old, internally contributed, or Marketplace-owned with unclear support ownership.
- Likely cause: many packages were Internal Labs or Marketplace contributions rather than supported official packages.
- Automatic remediation: for skill execution, treat ownership uncertainty as planning context only. Continue project-level analysis and safe package upgrades where a compatible package exists.
- Manual fallback: when no Windows-compatible package exists, route by package type: connection/API-heavy packages generally require Integration Service/product-team review; non-connection productivity/system packages generally route to the corresponding activities team. The broader strategy is: upgrade Marketplace package to Windows, communicate official alternatives, then enable a migration path from Marketplace activities to official activities.
- Validation: document package owner/status in the migration report and separate it from technical analyzer findings.

Add future entries in this format after any explicit refresh:

```text
### <short issue name>
- Applies to: <package/activity/framework>
- Symptoms: <errors, SARIF rule IDs, build messages>
- Likely cause: <concise cause>
- Automatic remediation: <safe fix the skill may apply>
- Manual fallback: <what remains if automation cannot decide safely>
- Validation: <analyze/build/run check>
```

## Baseline Operational Context

- Prefer migration in an output copy; do not mutate the original project unless explicitly approved.
- Use SARIF findings as the machine-readable source for remediation.
- Treat missing dependencies, unresolved namespaces, and unsupported activity conversions as remediation candidates first, not final user-facing blockers.
- Stop and ask before replacing activities when the replacement changes business behavior, credentials, selectors, queues, assets, or external service calls.
