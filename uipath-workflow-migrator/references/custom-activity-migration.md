# Custom Activity Package Migration

Use this reference when a migrated process depends on custom or third-party activity packages, or when the user asks whether the skill can migrate custom activities.

Official reference: https://docs.uipath.com/sdk/other/latest/developer-guide/migrating-activities-to-net

## Support Boundary

The normal Workflow Migrator process migrates UiPath projects that consume activities. It does not automatically migrate the source code of a custom activity package.

Supported today:

- Detect custom or third-party packages in `project.json`.
- Detect missing custom activity types or namespaces from SARIF and XAML.
- Report these packages as blockers or high-risk items.
- Guide the user to provide a Windows-compatible package, migrate the custom library first, or replace the custom activity behavior with supported activities, APIs, or coded workflow logic.

Not supported as an automatic built-in operation today:

- Convert custom activity source projects to SDK-style `.csproj`.
- Add or validate `.NET` target frameworks in the custom activity source.
- Rebuild, pack, sign, or publish the custom activity NuGet package.
- Prove behavior equivalence for custom activity runtime or designer code.
- Migrate binary-only `.nupkg` packages when source code is unavailable.

If the custom activity source repository is available, a coding agent can assist with parts of the source migration, but it must be treated as a separate package migration task before the consuming process is upgraded.

## User Steps

When a Windows-Legacy process depends on a custom activity package, use this sequence:

1. Identify every custom package and activity namespace used by the process.
2. Obtain the custom activity package source code, not only the `.nupkg`, when possible.
3. Confirm ownership, license, build prerequisites, private feed access, signing requirements, and target Studio version.
4. Migrate the custom activity project to SDK-style `.csproj`.
5. Multi-target the activity package so it can support the required runtimes, typically keeping the legacy target such as `net461` and adding a Windows target such as `net6.0-windows`.
6. Move package references into the `.csproj`; do not rely on `packages.config` for the migrated package.
7. Add the .NET workflow dependencies required by UiPath guidance, including `UiPath.Workflow.Runtime`, `UiPath.Workflow`, `System.Activities.Core.Presentation`, and `System.Activities.Metadata`, with appropriate target-framework conditions.
8. Check every third-party or internal dependency for `.NET` compatibility. Upgrade or replace dependencies that are .NET Framework-only.
9. Review activity runtime code and designer code for APIs that are unavailable or behave differently under `.NET`.
10. Build and test every target framework.
11. Create a NuGet package that contains the proper framework folders, for example `net461` and `net6.0-windows7.0`.
12. Do not include referenced packages inside the NuGet package or as bundled metadata in a way that causes Studio package installation failures.
13. Publish the migrated custom package to the package feed used by Studio/Robot.
14. Update or restore the consuming process against the migrated package.
15. Rerun Workflow Migrator analysis on the consuming process.
16. Upgrade the consuming process only after custom package restore, type loading, Studio validation, and representative runtime tests pass.

## Coding Agent Assistance

A coding agent can assist when source code is available:

- Inspect `.csproj`, `packages.config`, source files, designer files, and package metadata.
- Propose an SDK-style project file and target-framework conditions.
- Identify .NET Framework-only dependencies and APIs.
- Update project references and package references when the replacement versions are known.
- Run build/test/pack commands when the required SDKs and credentials are available.
- Produce a migration report showing remaining blockers and manual decisions.

Human or client input is still required for:

- Source/package ownership.
- Feed credentials and publication rights.
- Dependency replacement decisions.
- Licensing and signing requirements.
- Functional validation in Studio and in real consuming workflows.
- Business acceptance of behavior changes.

## Key Limitations

- Binary-only packages cannot be reliably migrated without source code. The practical options are to obtain source, request a vendor-provided Windows-compatible package, or replace the activities in the process.
- A package that compiles under `.NET` may still fail in Studio if designer dependencies, metadata, icons, localization resources, or package layout are invalid.
- Framework-specific APIs, native DLLs, COM dependencies, Windows-only assumptions, serialization behavior, and transitive dependencies can block migration.
- For latest STS validation, do not rely on STS to edit the original Windows-Legacy process. Validate the converted Windows process and migrated custom package in the target environment.

## Report Guidance

When custom packages are found, generated reports should state:

- Custom package migration is separate from process migration.
- The process migration is blocked or high-risk until a Windows-compatible custom package exists.
- If source is available, migrate and republish the package first using the custom activity package migration steps.
- If source is unavailable, choose between vendor/client republishing, replacing the custom activities, or redesigning the affected workflows.
- Validation requires clean package restore, no missing type findings, successful Studio open/build/analyze, and representative runtime tests for workflows that use the custom activities.
