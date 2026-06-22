#!/usr/bin/env python3
"""Run bundled UiPath.Upgrade.Cli with an optional consent-gated workflow."""

from __future__ import annotations

import argparse
import json
import os
import platform
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


CLI_EXE_NAME = "UiPath.Upgrade.exe"
CLI_DLL_NAME = "UiPath.Upgrade.dll"
DEFAULT_TOOL_DIR = Path("tools/uipath-upgrade-cli")
STOP_FOR_CONSENT_EXIT_CODE = 3


def skill_root() -> Path:
    return Path(__file__).resolve().parents[1]


def default_tool_root() -> Path:
    return skill_root() / DEFAULT_TOOL_DIR


def cli_candidates(tool_root: Path) -> list[Path]:
    candidates = [
        tool_root / CLI_EXE_NAME,
        tool_root / CLI_DLL_NAME,
    ]

    if tool_root.exists():
        candidates.extend(sorted(tool_root.rglob(CLI_EXE_NAME)))
        candidates.extend(sorted(tool_root.rglob(CLI_DLL_NAME)))

    return candidates


def locate_cli(cli_path: str | None, tool_root: str | None) -> Path | None:
    if cli_path:
        candidate = Path(cli_path).expanduser().resolve()
        return candidate if candidate.exists() else None

    env_cli = os.environ.get("UIPATH_UPGRADE_CLI")
    if env_cli:
        candidate = Path(env_cli).expanduser().resolve()
        if candidate.exists():
            return candidate

    root = Path(tool_root).expanduser().resolve() if tool_root else default_tool_root()
    for candidate in cli_candidates(root):
        if candidate.exists():
            return candidate.resolve()

    return None


def run_cli(cli: Path, cli_args: list[str]) -> int:
    if not cli_args:
        print(str(cli))
        return 0

    if cli.suffix.lower() == ".dll":
        command = ["dotnet", str(cli), *cli_args]
    else:
        if platform.system() != "Windows" and cli.suffix.lower() == ".exe":
            print(
                f"{cli} is a Windows executable. Run it on Windows or provide a compatible CLI path.",
                file=sys.stderr,
            )
            return 2
        command = [str(cli), *cli_args]

    return subprocess.run(command).returncode


def find_latest_sarif(project_path: Path) -> Path | None:
    upgrade_dir = project_path / ".upgrade"
    if not upgrade_dir.exists():
        return None

    sarif_files = [path for path in upgrade_dir.rglob("*.sarif") if path.is_file()]
    if not sarif_files:
        return None

    return max(sarif_files, key=lambda path: path.stat().st_mtime)


def load_sarif(path: Path | None) -> dict[str, Any] | None:
    if not path:
        return None

    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"Could not parse SARIF report {path}: {exc}", file=sys.stderr)
        return None


def summarize_sarif(sarif: dict[str, Any] | None) -> tuple[Counter[str], list[dict[str, str]]]:
    counts: Counter[str] = Counter()
    findings: list[dict[str, str]] = []

    if not sarif:
        return counts, findings

    for run in sarif.get("runs", []):
        for result in run.get("results", []):
            level = result.get("level") or "none"
            rule_id = result.get("ruleId") or result.get("rule", {}).get("id") or "unknown"
            message = result.get("message", {}).get("text") or result.get("message", {}).get("markdown") or ""
            location = ""
            locations = result.get("locations") or []
            if locations:
                artifact = (
                    locations[0]
                    .get("physicalLocation", {})
                    .get("artifactLocation", {})
                    .get("uri", "")
                )
                region = locations[0].get("physicalLocation", {}).get("region", {})
                line = region.get("startLine")
                location = f"{artifact}:{line}" if artifact and line else artifact

            counts[level] += 1
            findings.append(
                {
                    "level": level,
                    "rule_id": rule_id,
                    "message": message,
                    "location": location,
                }
            )

    return counts, findings


def write_analysis_report(
    report_path: Path,
    *,
    project_path: Path,
    output_path: Path | None,
    cli: Path,
    analyze_exit_code: int,
    sarif_path: Path | None,
    sarif: dict[str, Any] | None,
) -> Path:
    counts, findings = summarize_sarif(sarif)
    report_path.parent.mkdir(parents=True, exist_ok=True)

    lines = [
        "# UiPath Migration Analysis Report",
        "",
        f"- Generated UTC: {datetime.now(timezone.utc).isoformat()}",
        f"- Project path: `{project_path}`",
        f"- Planned output path: `{output_path or str(project_path) + '_Upgraded'}`",
        f"- Workflow Migrator CLI: `{cli}`",
        f"- Analyze exit code: `{analyze_exit_code}`",
        f"- SARIF source: `{sarif_path}`" if sarif_path else "- SARIF source: not found",
        "",
        "## Finding Counts",
        "",
    ]

    if counts:
        for level in ["error", "warning", "note", "none"]:
            lines.append(f"- {level}: {counts.get(level, 0)}")
    else:
        lines.append("- No SARIF findings were parsed.")

    lines.extend(["", "## Top Findings", ""])

    if findings:
        for finding in findings[:25]:
            message = finding["message"].replace("\n", " ").strip()
            location = f" ({finding['location']})" if finding["location"] else ""
            lines.append(f"- [{finding['level']}] `{finding['rule_id']}`{location}: {message}")
    else:
        lines.append("- No findings to list.")

    lines.extend(
        [
            "",
            "## Migration Gate",
            "",
            "Do not run `upgrade` until the user has reviewed this report and explicitly approved migration.",
            "After approval, rerun the helper with `--approve-migration`.",
            "",
        ]
    )

    report_path.write_text("\n".join(lines), encoding="utf-8")
    return report_path


def consent_gated_workflow(args: argparse.Namespace, cli: Path) -> int:
    project_path = Path(args.project_path).expanduser().resolve()
    if not project_path.exists():
        print(f"Project path does not exist: {project_path}", file=sys.stderr)
        return 2

    output_path = Path(args.output_path).expanduser().resolve() if args.output_path else None
    report_path = (
        Path(args.report_path).expanduser().resolve()
        if args.report_path
        else project_path / ".upgrade" / "migration-analysis-report.md"
    )

    passthrough = args.cli_args
    analyze_args = [
        "analyze",
        "--project-path",
        str(project_path),
        "--output-format",
        "sarif",
        *passthrough,
    ]
    if args.verbose and "--verbose" not in passthrough and "-v" not in passthrough:
        analyze_args.append("--verbose")

    analyze_exit_code = run_cli(cli, analyze_args)
    sarif_path = find_latest_sarif(project_path)
    sarif = load_sarif(sarif_path)
    report = write_analysis_report(
        report_path,
        project_path=project_path,
        output_path=output_path,
        cli=cli,
        analyze_exit_code=analyze_exit_code,
        sarif_path=sarif_path,
        sarif=sarif,
    )

    print(f"Analysis report: {report}")

    if analyze_exit_code != 0:
        print("Analyze failed. Review the report before attempting migration.", file=sys.stderr)
        return analyze_exit_code

    if not args.approve_migration:
        print(
            "Migration paused for user consent. Review the report, then rerun with --approve-migration.",
            file=sys.stderr,
        )
        return STOP_FOR_CONSENT_EXIT_CODE

    upgrade_args = [
        "upgrade",
        "--project-path",
        str(project_path),
        *passthrough,
    ]
    if output_path:
        upgrade_args.extend(["--output-path", str(output_path)])
    if args.verbose and "--verbose" not in passthrough and "-v" not in passthrough:
        upgrade_args.append("--verbose")

    return run_cli(cli, upgrade_args)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run bundled UiPath.Upgrade.exe and optionally enforce analyze/report/consent migration."
    )
    parser.add_argument("--cli", help="Path to a prebuilt UiPath.Upgrade.exe or UiPath.Upgrade.dll.")
    parser.add_argument("--tool-root", help="Directory containing the bundled UiPath.Upgrade.Cli files.")
    parser.add_argument("--locate", action="store_true", help="Print the located CLI path and exit.")
    parser.add_argument("--consent-gated", action="store_true", help="Run analyze, write a report, and stop unless migration is approved.")
    parser.add_argument("--project-path", help="UiPath project folder for --consent-gated.")
    parser.add_argument("--output-path", help="Planned output project folder for --consent-gated upgrade.")
    parser.add_argument("--report-path", help="Markdown report path. Defaults to <project>/.upgrade/migration-analysis-report.md.")
    parser.add_argument("--approve-migration", action="store_true", help="Allow the upgrade phase after analysis has completed.")
    parser.add_argument("--verbose", "-v", action="store_true", help="Pass --verbose to analyze/upgrade in --consent-gated mode.")
    parser.add_argument("cli_args", nargs=argparse.REMAINDER, help="Arguments passed to UiPath.Upgrade.exe after --.")
    args = parser.parse_args(argv)

    if args.cli_args and args.cli_args[0] == "--":
        args.cli_args = args.cli_args[1:]

    return args


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    cli = locate_cli(args.cli, args.tool_root)

    if args.locate:
        if not cli:
            print(
                f"Could not locate UiPath.Upgrade.Cli. Place it under {default_tool_root()} or pass --cli.",
                file=sys.stderr,
            )
            return 2
        print(str(cli))
        return 0

    if not cli:
        print(
            f"Could not locate UiPath.Upgrade.Cli. Place it under {default_tool_root()} or pass --cli.",
            file=sys.stderr,
        )
        return 2

    if args.consent_gated:
        if not args.project_path:
            print("--project-path is required with --consent-gated.", file=sys.stderr)
            return 2
        return consent_gated_workflow(args, cli)

    return run_cli(cli, args.cli_args)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
