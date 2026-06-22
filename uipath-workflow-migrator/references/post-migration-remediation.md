# Post-Migration Remediation

Use this reference after an approved upgrade finishes.

## Remediation Loop

1. Re-analyze the migrated output project with SARIF output.
2. Parse SARIF findings and inspect referenced files.
3. Read [migration-operations-knowledge.md](migration-operations-knowledge.md) for captured known issues and fixes.
4. Apply safe fixes directly in the output project.
5. Re-run analysis or build validation.
6. Repeat until findings are resolved or the remaining fixes require user decisions.

The helper performs a deterministic first pass. Codex should continue with agent-driven fixes for unresolved findings instead of only reporting them.

## Safe Automatic Fixes

Apply without asking when the change is limited to the migrated output folder and the intent is unambiguous:

- Correct `project.json` target framework if a Legacy value remains after a Legacy-to-Windows migration.
- Update package versions only when the SARIF finding, Upgrade CLI output, or captured operations knowledge gives an exact replacement.
- Fix XAML namespace/type references only when there is a one-to-one Modern replacement documented by the CLI report or captured knowledge.
- Remove stale generated migration artifacts from the output project if they block build validation and are not source workflows.
- Normalize project metadata that is clearly generated or migration-owned.

## Ask Before Fixing

Ask the user before changes that may alter business behavior:

- Replacing an unsupported activity with a different semantic operation.
- Changing selectors, credentials, queues, assets, Orchestrator folder bindings, connection names, or external endpoints.
- Editing the original source project instead of the migrated output copy.
- Choosing between multiple package versions or activity replacements.
- Disabling an extension, ignoring missing dependencies, or suppressing validation findings.

## Reporting

The final response should distinguish:

- Fixed automatically.
- Attempted but still failing.
- Not attempted because it requires a user decision or product support.

Include the remediation report path and the validation command that produced the final result.
