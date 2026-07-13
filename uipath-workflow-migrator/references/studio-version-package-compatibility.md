# Studio Version and Package Compatibility

Use this reference when explaining or changing how the skill reports package-version decisions for Windows-Legacy to Windows migrations.

## Official Guidance Reviewed

The skill behavior is based on the Windows-Legacy compatibility guidance for Studio 2024.10, Studio 2025.10, and latest STS.

Relevant scenarios to cover in generated reports:

- Inventory the project, dependencies, libraries, and external systems before upgrade.
- Convert and republish Windows-Legacy libraries before processes that consume them.
- Custom or third-party activity packages must be restored from configured feeds and must have Windows-compatible implementations.
- If a dependency cannot be resolved, converted workflows may contain unresolved activities and must not be treated as ready.
- Known expression issues such as ambiguous VB `{}` initializers require typed replacements such as `New Object() {}` when the target property expects an object array.
- SOAP web services are not supported in Windows or cross-platform projects.
- Latest STS no longer supports creating or editing Windows-Legacy source projects. Use a compatible conversion path for the source project, then validate the converted Windows project in STS.

## Package Version Selection

The skill does not independently choose arbitrary dependency versions. Package selection is primarily determined by the UiPath Upgrade CLI conversion pipeline, its migration extensions, and the package sources available to the CLI/Studio environment.

For general dependencies, UiPath Windows-Legacy compatibility guidance states:

- If the same package version exists in configured package sources, the version used by the Windows-Legacy project is kept.
- If the same version does not exist, the dependency is changed to the highest patch of the nearest available version.
- If no compatible package is available, the dependency remains unresolved and should be reported as a blocker.

The bundled CLI also exposes a targeted Mail/Microsoft 365 option:

```text
--outlook-package-version
```

The bundled CLI README documents the default as `3.1.21`. If the target Studio environment requires a different approved Microsoft Office 365 activities package version, pass this option explicitly and validate the converted project in that Studio version.

## Target Studio Version Handling

The helpers accept a target Studio version for reporting:

```powershell
-TargetStudioVersion "2024.10"
```

```bash
--target-studio-version "2025.10"
```

This value does not override UiPath package resolution by itself. It records the intended validation environment and tells the report how to frame compatibility checks.

Required validation:

- For Studio 2024.10, open/build/analyze the converted Windows project in Studio 2024.10 and use 2024.10-approved feeds/governance.
- For Studio 2025.10, open/build/analyze the converted Windows project in Studio 2025.10 and use 2025.10-approved feeds/governance.
- For latest STS, do not rely on STS to create/edit the original Windows-Legacy source project. Convert through a compatible path, then open/build/analyze the converted Windows project in STS.
- For any target version, verify the selected package versions restore from the same feeds the developer and robot will use.

## Reporting Requirement

Every assessment report should include a package-version section that answers:

- Which Studio version is the intended validation target.
- Whether an explicit Mail/Microsoft 365 package version override was supplied.
- That general dependency versions are selected by configured package sources and migration pipeline behavior, not by the skill inventing versions.
- What validation is required before the user approves migration.
