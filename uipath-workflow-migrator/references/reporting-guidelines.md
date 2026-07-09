# Migration Reporting Guidelines

Use these rules whenever the skill creates or changes migration reports.

## Report Contract

Every migration analysis report must be an assessment report, not a SARIF digest. Use this section order:

1. Executive Summary
2. Pre-Flight Status
3. Validation Evidence
4. Migration Risks and Limitations
5. Migration Risks
6. Blockers
7. Automated Changes Detected
8. Resolution Order
9. Final Recommendation
10. Official Guidance Used
11. Finding Counts
12. Analysis Context
13. Raw Analyzer Output (only when explicitly requested)
14. Migration Gate (only when explicitly requested)

Keep raw analyzer and test-style log output out of the default report. Include it near the end only when the user explicitly asks for raw analyzer details. Include the Migration Gate section only when the user explicitly asks for the consent reminder to appear inside the report. The first sections must answer whether the user can approve the migration, what can break, who owns each issue, what can be automated, and how the outcome should be validated.

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

## Required Wording

- Explain risk in plain language instead of only showing SARIF rule IDs.
- Include owner, automation eligibility, resolution steps, and validation guidance for every risk row.
- Always include the limitations section, even for clean migrations.
- Keep upgrade consent enforced by workflow behavior even when the Migration Gate section is omitted from the report.
