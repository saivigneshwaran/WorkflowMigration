# Migration Reporting Guidelines

Use these rules whenever the skill creates or changes migration reports.

## Report Contract

Every migration analysis report must be an assessment report, not a SARIF digest. Use this section order:

1. Executive Summary
2. Pre-Flight Status
3. Validation Evidence
4. Package Version Selection and Studio Compatibility
5. Migration Risks and Limitations
6. Migration Risks
7. Blockers
8. How to Address Findings
9. Automated Changes Detected
10. Resolution Order
11. Final Recommendation
12. Official Guidance Used
13. Finding Counts
14. Analysis Context
15. Raw Analyzer Output (only when explicitly requested)
16. Migration Gate (only when explicitly requested)

Keep raw analyzer and test-style log output out of the default report. Include it near the end only when the user explicitly asks for raw analyzer details. Include the Migration Gate section only when the user explicitly asks for the consent reminder to appear inside the report. The first sections must answer whether the user can approve the migration, what can break, who owns each issue, what can be automated, how package compatibility should be validated for the target Studio version, and how the outcome should be validated.

## Readiness Values

- `Blocked`: analyzer exits non-zero, SARIF is missing, or any blocking finding exists.
- `High Risk`: no blocking findings, but high-risk custom packages, unsupported activities, or attention items exist.
- `Ready With Warnings`: only medium-risk warnings remain.
- `Ready`: no errors, warnings, or attention items.

## Classification Rules

- Missing package or restore failure: Blocking Issues.
- Invalid XAML, type check failure, validation failure, or analyzer error: Blocking Issues.
- Unsupported, manual, custom, or legacy activity findings: Activities and Packages Requiring Attention.
- Package upgrades, package migrations, UI Automation migration, Mail migration, Office 365 migration, and framework updates: Automated Changes Detected.
- Successful project load, successful XAML parse, and successful package restore messages: Raw Analyzer Output.
- If restore blockers are present, run a second analyze pass with `--ignore-missing-dependencies` when that option was not already provided. Use it to uncover deeper migration findings while keeping the original restore blocker visible.
- Extract concrete activity names and workflow locations from SARIF and XAML whenever possible.
- Add risk rows for common runtime migration issues: custom/third-party packages, missing activity types, ambiguous VB expressions such as `{}`, unsupported `SaveImage`, classic UI Automation, image/OCR activities, GSuite/Microsoft 365 connection IDs, SMTP/mail settings, hardcoded configuration values, and SOAP/web-service usage.
- Include target Studio version and package-version selection guidance. General dependency versions are selected by the Upgrade CLI/migration pipeline and configured package feeds. Explicitly mention `--outlook-package-version` only for Mail/Microsoft 365 migration package selection.

## Required Wording

- Explain risk in plain language instead of only showing SARIF rule IDs.
- Include owner, automation eligibility, resolution steps, and validation guidance for every risk row.
- Include a `How to Address Findings` section with per-risk fix guidance, coding-agent responsibilities, human/client responsibilities, preferred replacement, and validation.
- Always include the limitations section, even for clean migrations.
- Keep upgrade consent enforced by workflow behavior even when the Migration Gate section is omitted from the report.
