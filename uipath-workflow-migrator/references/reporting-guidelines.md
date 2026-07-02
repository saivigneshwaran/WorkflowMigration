# Migration Reporting Guidelines

Use these rules whenever the skill creates or changes migration reports.

## Report Contract

Every migration analysis report must use this section order:

1. Executive Summary
2. Analysis Context
3. Migration Risks and Limitations
4. Blocking Issues
5. Activities and Packages Requiring Attention
6. Automated Changes Detected
7. Required User Actions
8. Approval Recommendation
9. Finding Counts
10. Raw Analyzer Output
11. Migration Gate

Keep raw analyzer and test-style log output near the end. The first sections must answer whether the user can approve the migration, what can break, and what needs attention.

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

## Required Wording

- Explain risk in plain language instead of only showing SARIF rule IDs.
- Include a required action for every blocking or attention item.
- Always include the limitations section, even for clean migrations.
- Always include the migration gate reminding the user that upgrade requires explicit approval.
