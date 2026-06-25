# Workflow Migration Agent Instructions

This repository contains one self-contained AI coding-agent skill for UiPath workflow migration.

## Skill Discovery

- Primary skill folder: `uipath-workflow-migrator/`
- UiPath-style discovery alias: `skills/uipath-workflow-migrator`
- Codex-style discovery alias: `.agents/skills`

When a user asks to analyze or migrate UiPath Studio projects, read `uipath-workflow-migrator/SKILL.md` before acting. The skill owns the migration workflow, bundled helper script, references, and bundled UiPath Upgrade CLI.

Use `python3 scripts/install_skill.py --agent all --mode copy` from the repository root for the common local installation path. Use `--target <skills-dir>` for an agent-specific skills directory.

## Repository Rules

- Keep the skill self-contained; everything required for normal execution must remain reachable from `SKILL.md`.
- Keep agent-specific wiring in root metadata files, not inside the skill body.
- Use `references/migration-operations-knowledge.md` during migration work instead of querying external knowledge sources during normal execution.
- Do not write to the original source project during migration unless the user explicitly approves that change.
- Run actual `UiPath.Upgrade.Cli` operations on Windows with the required .NET runtime and package/feed access.
