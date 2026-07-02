#!/usr/bin/env python3
"""Run bundled UiPath.Upgrade.Cli with an optional consent-gated workflow."""

from __future__ import annotations

import argparse
import json
import os
import platform
import subprocess
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
import re
from typing import Any


CLI_EXE_NAME = "UiPath.Upgrade.exe"
CLI_DLL_NAME = "UiPath.Upgrade.dll"
DEFAULT_TOOL_DIR = Path("tools/uipath-upgrade-cli")
STOP_FOR_CONSENT_EXIT_CODE = 3
DEFAULT_POLL_INTERVAL_SECONDS = 60.0
MIN_POLL_INTERVAL_SECONDS = 5.0


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


def env_status_mode() -> str:
    mode = os.environ.get("UIPATH_MIGRATOR_STATUS_MODE", "wait").strip().lower()
    return mode if mode in {"wait", "poll"} else "wait"


def parse_poll_interval(value: str | None) -> float:
    if not value:
        return DEFAULT_POLL_INTERVAL_SECONDS

    try:
        interval = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("poll interval must be a number") from exc

    if interval < MIN_POLL_INTERVAL_SECONDS:
        raise argparse.ArgumentTypeError(
            f"poll interval must be at least {MIN_POLL_INTERVAL_SECONDS:g} seconds"
        )
    return interval


def env_poll_interval() -> float:
    try:
        return parse_poll_interval(os.environ.get("UIPATH_MIGRATOR_POLL_INTERVAL_SECONDS"))
    except argparse.ArgumentTypeError:
        return DEFAULT_POLL_INTERVAL_SECONDS


def run_process(
    command: list[str],
    *,
    status_mode: str,
    poll_interval_seconds: float,
    operation_name: str,
) -> int:
    if status_mode == "wait":
        return subprocess.run(command).returncode

    process = subprocess.Popen(command)
    started = time.monotonic()

    try:
        while True:
            try:
                return process.wait(timeout=poll_interval_seconds)
            except subprocess.TimeoutExpired:
                elapsed = int(time.monotonic() - started)
                print(
                    f"{operation_name} still running after {elapsed}s; "
                    f"next status check in {poll_interval_seconds:g}s.",
                    file=sys.stderr,
                    flush=True,
                )
    except KeyboardInterrupt:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
        return 130


def run_cli(
    cli: Path,
    cli_args: list[str],
    *,
    status_mode: str = "wait",
    poll_interval_seconds: float = DEFAULT_POLL_INTERVAL_SECONDS,
    operation_name: str = "UiPath.Upgrade.Cli",
) -> int:
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

    return run_process(
        command,
        status_mode=status_mode,
        poll_interval_seconds=poll_interval_seconds,
        operation_name=operation_name,
    )


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


def normalize_text(value: str) -> str:
    return " ".join(value.replace("\n", " ").split())


def markdown_escape(value: str) -> str:
    return normalize_text(value).replace("|", "\\|")


def project_dependencies(project_path: Path) -> dict[str, str]:
    project_json = project_path / "project.json"
    if not project_json.exists():
        return {}

    try:
        project = json.loads(project_json.read_text(encoding="utf-8"))
    except Exception:
        return {}

    dependencies = project.get("dependencies")
    return dependencies if isinstance(dependencies, dict) else {}


def project_target_framework(project_path: Path) -> str:
    project_json = project_path / "project.json"
    if not project_json.exists():
        return "unknown"

    try:
        project = json.loads(project_json.read_text(encoding="utf-8"))
    except Exception:
        return "unknown"

    return str(project.get("targetFramework") or "unknown")


def custom_dependency_items(project_path: Path) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    for name, version in sorted(project_dependencies(project_path).items()):
        lower = name.lower()
        if lower.startswith("uipath.") or lower in {"newtonsoft.json"}:
            continue
        items.append(
            {
                "area": "Package",
                "item": f"{name} {version}",
                "risk": "High",
                "impact": "Custom or third-party package must be available and Windows-compatible.",
                "action": "Confirm package source, compatibility, or replacement before approving upgrade.",
            }
        )
    return items


def custom_namespace_items(project_path: Path) -> list[dict[str, str]]:
    namespace_pattern = re.compile(r"xmlns:[A-Za-z0-9_]+=[\"']([^\"']+)[\"']")
    assembly_pattern = re.compile(r"assembly=([^;\"']+)")
    ignored_prefixes = (
        "System",
        "Microsoft.",
        "Microsoft",
        "UiPath.",
        "UiPath",
        "Newtonsoft.",
        "Newtonsoft",
        "Google.",
        "Google",
        "mscorlib",
    )
    counts: Counter[str] = Counter()

    for xaml in project_path.rglob("*.xaml"):
        if ".upgrade" in xaml.parts:
            continue
        try:
            text = xaml.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        for namespace in namespace_pattern.findall(text):
            match = assembly_pattern.search(namespace)
            if not match:
                continue
            assembly = match.group(1)
            if assembly.startswith(ignored_prefixes):
                continue
            counts[assembly] += 1

    return [
        {
            "area": "Activity namespace",
            "item": f"{assembly} ({count} XAML reference{'s' if count != 1 else ''})",
            "risk": "High",
            "impact": "Custom activity namespaces may not load after Windows migration.",
            "action": "Confirm a Windows-compatible package exists and validate affected workflows.",
        }
        for assembly, count in sorted(counts.items())
    ]


def package_from_message(message: str) -> str:
    match = re.search(r"[Pp]ackage '([^']+)'(?: version '([^']+)')?", message)
    if not match:
        return ""
    if match.group(2):
        return f"{match.group(1)} {match.group(2)}"
    return match.group(1)


def classify_finding(finding: dict[str, str]) -> dict[str, str]:
    rule_id = finding["rule_id"]
    rule = rule_id.upper()
    level = finding["level"].lower()
    message = normalize_text(finding["message"])
    message_lower = message.lower()
    location = finding["location"]

    classification = {
        "level": finding["level"],
        "rule_id": rule_id,
        "location": location,
        "message": message,
        "category": "Raw Analyzer Output",
        "severity": "Info",
        "plain_language": message or "Analyzer event.",
        "required_action": "No action required.",
    }

    if "RESTORE-MISSING-PACKAGE" in rule or (
        "package" in message_lower and "not found" in message_lower
    ):
        package = package_from_message(message) or "Package"
        classification.update(
            {
                "category": "Blocking Issues",
                "severity": "Blocking",
                "plain_language": f"{package} is not available from the configured package feeds.",
                "required_action": "Add the package feed, restore the package, or identify a Windows-compatible replacement before approving upgrade.",
            }
        )
    elif any(token in rule for token in ["TYPECHECK", "VALIDATE", "XAML-WORKFLOW-PARSE"]) and (
        level == "error" or any(word in message_lower for word in ["invalid", "failed", "error"])
    ):
        classification.update(
            {
                "category": "Blocking Issues",
                "severity": "Blocking",
                "plain_language": "Workflow validation or parsing failed.",
                "required_action": "Fix the referenced workflow issue and rerun analysis before approving upgrade.",
            }
        )
    elif level == "error":
        classification.update(
            {
                "category": "Blocking Issues",
                "severity": "Blocking",
                "plain_language": message or "Analyzer reported an error.",
                "required_action": "Resolve this error and rerun analysis before approving upgrade.",
            }
        )
    elif any(token in rule for token in ["UNSUPPORTED", "MANUAL", "CUSTOM", "LEGACY-ACTIVITY"]):
        classification.update(
            {
                "category": "Activities and Packages Requiring Attention",
                "severity": "High",
                "plain_language": message or "Analyzer found an item requiring migration attention.",
                "required_action": "Review the activity or package and decide whether a compatible replacement is required.",
            }
        )
    elif any(token in rule for token in ["MAIL", "OFFICE365", "UIAUTOMATION", "PACKAGE-UPGRADE", "PACKAGE-MIGRATION", "FRAMEWORK-UPDATE"]):
        classification.update(
            {
                "category": "Automated Changes Detected",
                "severity": "Info",
                "plain_language": message or "The analyzer identified an automatic migration change.",
                "required_action": "Validate behavior after upgrade, especially authentication, selectors, and external service calls.",
            }
        )
    elif level == "warning":
        classification.update(
            {
                "category": "Activities and Packages Requiring Attention",
                "severity": "Medium",
                "plain_language": message or "Analyzer reported a warning.",
                "required_action": "Review before approving upgrade.",
            }
        )

    return classification


def classify_findings(findings: list[dict[str, str]]) -> list[dict[str, str]]:
    return [classify_finding(finding) for finding in findings]


def readiness_status(analyze_exit_code: int, classified: list[dict[str, str]], sarif_path: Path | None) -> str:
    if analyze_exit_code != 0 or any(item["severity"] == "Blocking" for item in classified):
        return "Blocked"
    if not sarif_path:
        return "Blocked"
    if any(item["severity"] == "High" for item in classified):
        return "High Risk"
    if any(item["severity"] == "Medium" for item in classified):
        return "Ready With Warnings"
    return "Ready"


def approval_recommendation(status: str) -> str:
    if status == "Blocked":
        return "Do not approve upgrade yet. Resolve blocking issues and rerun analysis."
    if status == "High Risk":
        return "Approve only after reviewing the highlighted activities/packages and accepting validation risk."
    if status == "Ready With Warnings":
        return "Approve only after reviewing warnings and planned validation."
    return "Ready for approval, subject to normal post-upgrade validation."


def add_table(lines: list[str], headers: list[str], rows: list[list[str]]) -> None:
    lines.append("| " + " | ".join(headers) + " |")
    lines.append("| " + " | ".join("---" for _ in headers) + " |")
    for row in rows:
        lines.append("| " + " | ".join(markdown_escape(value) for value in row) + " |")


def has_cli_option(args: list[str], *names: str) -> bool:
    for arg in args:
        if any(arg == name or arg.startswith(f"{name}=") for name in names):
            return True
    return False


def build_analyze_args(project_path: Path, passthrough: list[str], verbose: bool) -> list[str]:
    analyze_args = [
        "analyze",
        "--project-path",
        str(project_path),
    ]
    if not has_cli_option(passthrough, "--output-format", "-f"):
        analyze_args.extend(["--output-format", "sarif"])
    analyze_args.extend(passthrough)
    if verbose and not has_cli_option(passthrough, "--verbose", "-v"):
        analyze_args.append("--verbose")
    return analyze_args


def default_output_path(project_path: Path) -> Path:
    return Path(f"{project_path}_Upgraded")


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
    classified = classify_findings(findings)
    status = readiness_status(analyze_exit_code, classified, sarif_path)
    blocking = [item for item in classified if item["category"] == "Blocking Issues"]
    automated = [item for item in classified if item["category"] == "Automated Changes Detected"]
    attention = [
        item for item in classified if item["category"] == "Activities and Packages Requiring Attention"
    ]
    project_attention = custom_dependency_items(project_path) + custom_namespace_items(project_path)
    report_path.parent.mkdir(parents=True, exist_ok=True)

    lines = [
        "# UiPath Migration Analysis Report",
        "",
        "## Executive Summary",
        "",
        f"- Migration readiness: **{status}**",
        f"- Approval recommendation: {approval_recommendation(status)}",
        f"- Source target framework: `{project_target_framework(project_path)}`",
        "- Target migration: `Windows`",
        f"- Analyzer exit code: `{analyze_exit_code}`",
        f"- Blocking issues: `{len(blocking)}`",
        f"- Activities/packages requiring attention: `{len(attention) + len(project_attention)}`",
        f"- Automated changes detected: `{len(automated)}`",
        "",
        "## Analysis Context",
        "",
        f"- Generated UTC: {datetime.now(timezone.utc).isoformat()}",
        f"- Project path: `{project_path}`",
        f"- Planned output path: `{output_path or str(project_path) + '_Upgraded'}`",
        f"- Workflow Migrator CLI: `{cli}`",
        f"- SARIF source: `{sarif_path}`" if sarif_path else "- SARIF source: not found",
        "",
        "## Migration Risks and Limitations",
        "",
        "- The analyzer can identify package, parsing, validation, and supported migration findings, but it cannot prove runtime business equivalence.",
        "- Selectors, credentials, Orchestrator assets, queues, connection names, file paths, and external service behavior must be validated after upgrade.",
        "- Custom and third-party activity packages require special review because Windows compatibility depends on the package implementation and available feeds.",
        "- Mail, Office 365, UI Automation, PDF, Excel, and external application behavior should be tested with representative non-production data.",
        "- A clean analysis report does not replace opening/building the migrated project in Studio and running targeted workflow tests.",
        "",
        "## Blocking Issues",
        "",
    ]

    if blocking:
        add_table(
            lines,
            ["Rule", "Location", "Issue", "Required action"],
            [
                [
                    item["rule_id"],
                    item["location"] or "-",
                    item["plain_language"],
                    item["required_action"],
                ]
                for item in blocking
            ],
        )
    else:
        lines.append("- None found.")

    lines.extend(["", "## Activities and Packages Requiring Attention", ""])

    attention_rows = [
        [
            item["rule_id"],
            item["location"] or "-",
            item["severity"],
            item["plain_language"],
            item["required_action"],
        ]
        for item in attention
    ]
    attention_rows.extend(
        [
            [item["area"], item["item"], item["risk"], item["impact"], item["action"]]
            for item in project_attention
        ]
    )
    if attention_rows:
        add_table(lines, ["Area", "Item", "Risk", "Impact", "Required action"], attention_rows)
    else:
        lines.append("- None found.")

    lines.extend(["", "## Automated Changes Detected", ""])

    if automated:
        add_table(
            lines,
            ["Rule", "Location", "Detected change", "Validation required"],
            [
                [
                    item["rule_id"],
                    item["location"] or "-",
                    item["plain_language"],
                    item["required_action"],
                ]
                for item in automated
            ],
        )
    else:
        lines.append("- None found.")

    lines.extend(["", "## Required User Actions", ""])
    required_actions: list[str] = []
    for item in blocking + attention:
        action = item["required_action"]
        if action not in required_actions:
            required_actions.append(action)
    for item in project_attention:
        action = item["action"]
        if action not in required_actions:
            required_actions.append(action)

    if required_actions:
        lines.extend(f"- {action}" for action in required_actions)
    else:
        lines.append("- Review the automated changes and run normal post-upgrade validation.")

    lines.extend(["", "## Approval Recommendation", "", approval_recommendation(status), ""])
    lines.extend(["", "## Finding Counts", ""])

    if counts:
        for level in ["error", "warning", "note", "none"]:
            lines.append(f"- {level}: {counts.get(level, 0)}")
    else:
        lines.append("- No SARIF findings were parsed.")

    lines.extend(["", "## Raw Analyzer Output", ""])

    if classified:
        for item in classified:
            location = f" ({item['location']})" if item["location"] else ""
            lines.append(
                f"- [{item['level']}] `{item['rule_id']}`{location}: {item['message']}"
            )
    else:
        lines.append("- No analyzer findings to list.")

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


def apply_safe_remediations(project_path: Path, findings: list[dict[str, str]]) -> list[str]:
    actions: list[str] = []
    project_json = project_path / "project.json"
    if not project_json.exists():
        return actions

    try:
        project = json.loads(project_json.read_text(encoding="utf-8"))
    except Exception as exc:
        return [f"Skipped project.json remediation because it could not be parsed: {exc}"]

    target_framework = project.get("targetFramework")
    if target_framework in {"Legacy", "Windows-Legacy"}:
        project["targetFramework"] = "Windows"
        project_json.write_text(json.dumps(project, indent=2) + "\n", encoding="utf-8")
        actions.append(
            f"Updated project.json targetFramework from {target_framework!r} to 'Windows'."
        )

    return actions


def write_remediation_report(
    report_path: Path,
    *,
    project_path: Path,
    pre_analyze_exit_code: int | None,
    post_analyze_exit_code: int | None,
    pre_sarif_path: Path | None,
    final_sarif_path: Path | None,
    final_sarif: dict[str, Any] | None,
    actions: list[str],
) -> Path:
    counts, findings = summarize_sarif(final_sarif)
    report_path.parent.mkdir(parents=True, exist_ok=True)

    lines = [
        "# UiPath Post-Migration Remediation Report",
        "",
        f"- Generated UTC: {datetime.now(timezone.utc).isoformat()}",
        f"- Migrated project path: `{project_path}`",
        f"- Initial post-upgrade analyze exit code: `{pre_analyze_exit_code}`",
        f"- Post-remediation analyze exit code: `{post_analyze_exit_code}`",
        f"- Initial SARIF source: `{pre_sarif_path}`" if pre_sarif_path else "- Initial SARIF source: not found",
        f"- Final SARIF source: `{final_sarif_path}`" if final_sarif_path else "- Final SARIF source: not found",
        "",
        "## Safe Remediation Actions",
        "",
    ]

    if actions:
        lines.extend(f"- {action}" for action in actions)
    else:
        lines.append("- No deterministic safe remediation pattern matched.")

    lines.extend(["", "## Remaining Finding Counts", ""])
    if counts:
        for level in ["error", "warning", "note", "none"]:
            lines.append(f"- {level}: {counts.get(level, 0)}")
    else:
        lines.append("- No SARIF findings were parsed.")

    lines.extend(["", "## Remaining Top Findings", ""])
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
            "## Next Step",
            "",
            "Resolve remaining findings manually only when no safe automatic remediation is available.",
            "",
        ]
    )

    report_path.write_text("\n".join(lines), encoding="utf-8")
    return report_path


def run_post_migration_remediation(
    args: argparse.Namespace,
    cli: Path,
    output_path: Path,
    passthrough: list[str],
) -> None:
    report_path = output_path / ".upgrade" / "post-migration-remediation-report.md"
    if not output_path.exists():
        report_path = output_path.parent / f"{output_path.name}-post-migration-remediation-report.md"
        report = write_remediation_report(
            report_path,
            project_path=output_path,
            pre_analyze_exit_code=None,
            post_analyze_exit_code=None,
            pre_sarif_path=None,
            final_sarif_path=None,
            final_sarif=None,
            actions=[f"Skipped remediation because the migrated output path does not exist: {output_path}"],
        )
        print(f"Post-migration remediation report: {report}")
        return

    analyze_args = build_analyze_args(output_path, passthrough, args.verbose)
    pre_exit_code = run_cli(
        cli,
        analyze_args,
        status_mode=args.status_mode,
        poll_interval_seconds=args.poll_interval_seconds,
        operation_name="post-upgrade analysis",
    )
    pre_sarif_path = find_latest_sarif(output_path)
    pre_sarif = load_sarif(pre_sarif_path)
    _, pre_findings = summarize_sarif(pre_sarif)
    actions = apply_safe_remediations(output_path, pre_findings)

    if actions:
        post_exit_code = run_cli(
            cli,
            analyze_args,
            status_mode=args.status_mode,
            poll_interval_seconds=args.poll_interval_seconds,
            operation_name="post-remediation analysis",
        )
        final_sarif_path = find_latest_sarif(output_path)
        final_sarif = load_sarif(final_sarif_path)
    else:
        post_exit_code = pre_exit_code
        final_sarif_path = pre_sarif_path
        final_sarif = pre_sarif

    report = write_remediation_report(
        report_path,
        project_path=output_path,
        pre_analyze_exit_code=pre_exit_code,
        post_analyze_exit_code=post_exit_code,
        pre_sarif_path=pre_sarif_path,
        final_sarif_path=final_sarif_path,
        final_sarif=final_sarif,
        actions=actions,
    )
    print(f"Post-migration remediation report: {report}")


def consent_gated_workflow(args: argparse.Namespace, cli: Path) -> int:
    project_path = Path(args.project_path).expanduser().resolve()
    if not project_path.exists():
        print(f"Project path does not exist: {project_path}", file=sys.stderr)
        return 2

    output_path = Path(args.output_path).expanduser().resolve() if args.output_path else None
    resolved_output_path = output_path or default_output_path(project_path)
    report_path = (
        Path(args.report_path).expanduser().resolve()
        if args.report_path
        else project_path / ".upgrade" / "migration-analysis-report.md"
    )

    passthrough = args.cli_args
    analyze_args = build_analyze_args(project_path, passthrough, args.verbose)

    analyze_exit_code = run_cli(
        cli,
        analyze_args,
        status_mode=args.status_mode,
        poll_interval_seconds=args.poll_interval_seconds,
        operation_name="migration analysis",
    )
    sarif_path = find_latest_sarif(project_path)
    sarif = load_sarif(sarif_path)
    report = write_analysis_report(
        report_path,
        project_path=project_path,
        output_path=resolved_output_path,
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
    if args.verbose and not has_cli_option(passthrough, "--verbose", "-v"):
        upgrade_args.append("--verbose")

    upgrade_exit_code = run_cli(
        cli,
        upgrade_args,
        status_mode=args.status_mode,
        poll_interval_seconds=args.poll_interval_seconds,
        operation_name="migration upgrade",
    )
    if not args.skip_remediation:
        run_post_migration_remediation(args, cli, resolved_output_path, passthrough)
    return upgrade_exit_code


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
    parser.add_argument(
        "--status-mode",
        choices=["wait", "poll"],
        default=env_status_mode(),
        help="Use wait to block until the CLI exits, or poll to print coarse status updates.",
    )
    parser.add_argument(
        "--poll-interval-seconds",
        type=parse_poll_interval,
        default=env_poll_interval(),
        help="Status update interval for --status-mode poll. Defaults to 60 seconds.",
    )
    parser.add_argument(
        "--skip-remediation",
        action="store_true",
        help="Skip the automatic post-upgrade analyze/remediation pass.",
    )
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

    return run_cli(
        cli,
        args.cli_args,
        status_mode=args.status_mode,
        poll_interval_seconds=args.poll_interval_seconds,
    )


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
