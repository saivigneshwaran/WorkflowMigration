#!/usr/bin/env python3
"""Run bundled UiPath.Upgrade.Cli with an optional consent-gated workflow."""

from __future__ import annotations

import argparse
import html
import json
import os
import platform
import re
import subprocess
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
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


def project_name(project_path: Path) -> str:
    project_json = project_path / "project.json"
    if not project_json.exists():
        return project_path.name

    try:
        project = json.loads(project_json.read_text(encoding="utf-8"))
    except Exception:
        return project_path.name

    return str(project.get("name") or project_path.name)


def format_examples(values: list[str], limit: int = 8) -> str:
    unique: list[str] = []
    for value in values:
        if value and value not in unique:
            unique.append(value)
    if not unique:
        return "-"
    suffix = f"; +{len(unique) - limit} more" if len(unique) > limit else ""
    return "; ".join(unique[:limit]) + suffix


def read_xaml_files(project_path: Path) -> list[tuple[Path, list[str]]]:
    files: list[tuple[Path, list[str]]] = []
    for xaml in sorted(project_path.rglob("*.xaml")):
        if ".upgrade" in xaml.parts:
            continue
        try:
            files.append((xaml, xaml.read_text(encoding="utf-8", errors="ignore").splitlines()))
        except Exception:
            continue
    return files


def relative_location(project_path: Path, path: Path, line_number: int | None = None) -> str:
    try:
        relative = path.relative_to(project_path)
    except ValueError:
        relative = path
    if line_number:
        return f"{relative}:{line_number}"
    return str(relative)


def xaml_attr(fragment: str, name: str) -> str:
    match = re.search(rf"\b{name}=[\"']([^\"']*)[\"']", fragment)
    return html.unescape(match.group(1)) if match else ""


def activity_display(fragment: str, class_name: str) -> str:
    display_name = xaml_attr(fragment, "DisplayName")
    return display_name or class_name


def activity_records(project_path: Path) -> list[dict[str, str]]:
    records: list[dict[str, str]] = []
    tag_pattern = re.compile(r"<([A-Za-z_][\w.-]*:)?([A-Za-z_][\w.]*)\b")

    for path, lines in read_xaml_files(project_path):
        for index, line in enumerate(lines):
            match = tag_pattern.search(line)
            if not match:
                continue
            class_name = match.group(2)
            if "." in class_name:
                continue
            window = " ".join(lines[index : min(index + 4, len(lines))])
            display = activity_display(window, class_name)
            records.append(
                {
                    "class": class_name,
                    "display": display,
                    "location": relative_location(project_path, path, index + 1),
                    "fragment": normalize_text(window),
                }
            )

    return records


def matching_activities(records: list[dict[str, str]], names: set[str]) -> list[dict[str, str]]:
    lowered = {name.lower() for name in names}
    return [record for record in records if record["class"].lower() in lowered]


def matching_fragments(
    project_path: Path,
    patterns: list[re.Pattern[str]],
    *,
    limit: int = 25,
) -> list[str]:
    matches: list[str] = []
    for path, lines in read_xaml_files(project_path):
        for index, line in enumerate(lines):
            if any(pattern.search(line) for pattern in patterns):
                snippet = normalize_text(html.unescape(line))
                matches.append(f"{relative_location(project_path, path, index + 1)} {snippet}")
                if len(matches) >= limit:
                    return matches
    return matches


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


def dedupe_findings(findings: list[dict[str, str]]) -> list[dict[str, str]]:
    seen: set[tuple[str, str, str, str]] = set()
    unique: list[dict[str, str]] = []
    for finding in findings:
        key = (
            finding.get("level", ""),
            finding.get("rule_id", ""),
            normalize_text(finding.get("message", "")),
            finding.get("location", ""),
        )
        if key in seen:
            continue
        seen.add(key)
        unique.append(finding)
    return unique


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


def risk_item(
    *,
    severity: str,
    location: str,
    component: str,
    failure_mode: str,
    replacement: str,
    resolution: str,
    owner: str,
    automation: str,
    validation: str,
    evidence: str,
) -> dict[str, str]:
    return {
        "severity": severity,
        "location": location,
        "component": component,
        "failure_mode": failure_mode,
        "replacement": replacement,
        "resolution": resolution,
        "owner": owner,
        "automation": automation,
        "validation": validation,
        "evidence": evidence,
    }


def sarif_examples(classified: list[dict[str, str]], predicate: Any) -> list[str]:
    examples: list[str] = []
    for item in classified:
        if predicate(item):
            location = item["location"] or "-"
            message = item["message"] or item["plain_language"]
            examples.append(f"{location} `{item['rule_id']}` {message}")
    return examples


def activity_examples(records: list[dict[str, str]], names: set[str], limit: int = 8) -> list[str]:
    return [
        f"{record['location']} `{record['display']}` ({record['class']})"
        for record in matching_activities(records, names)[:limit]
    ]


def has_dependency(project_path: Path, *package_names: str) -> bool:
    dependencies = {name.lower() for name in project_dependencies(project_path)}
    return any(package_name.lower() in dependencies for package_name in package_names)


def build_assessment_risks(
    project_path: Path,
    classified: list[dict[str, str]],
) -> list[dict[str, str]]:
    records = activity_records(project_path)
    risks: list[dict[str, str]] = []

    type_missing_examples = sarif_examples(
        classified,
        lambda item: "TYPE-MISSING" in item["rule_id"].upper()
        or "type" in item["message"].lower()
        and "not found" in item["message"].lower(),
    )
    missing_package_examples = sarif_examples(
        classified,
        lambda item: item["category"] == "Blocking Issues"
        and (
            "RESTORE-MISSING-PACKAGE" in item["rule_id"].upper()
            or "not available from the configured package feeds" in item["plain_language"]
            or ("package" in item["message"].lower() and "not found" in item["message"].lower())
        ),
    )
    missing_dependencies = [
        f"{name} {version}"
        for name, version in sorted(project_dependencies(project_path).items())
        if not name.lower().startswith("uipath.") and name.lower() != "newtonsoft.json"
    ]
    if missing_package_examples or missing_dependencies:
        risks.append(
            risk_item(
                severity="Blocker" if missing_package_examples else "High",
                location="project.json dependencies",
                component=format_examples(missing_dependencies) if missing_dependencies else "Package restore",
                failure_mode="Dependency restore or type resolution can fail; converted workflows may contain unresolved activities.",
                replacement="Migrate and publish Windows-compatible custom activity libraries first, or replace unavailable custom activities with supported UI Automation, API, or coded workflow implementations.",
                resolution="Treat custom activity package migration as a separate source/package task. Identify the owning library/feed, obtain source when possible, migrate the activity project to SDK-style .csproj with a Windows .NET target, validate dependencies, build/pack/publish the Windows-compatible package, update feeds if needed, then rerun normal analysis and the ignore-missing-dependencies pass.",
                owner="Client Owner + Human + Coding Agent",
                automation="Partial: the coding agent can map namespaces to packages, inspect and update custom activity source when provided, update project references, and rerun validation; humans must provide package ownership, feed credentials, source access, publication approval, and runtime validation.",
                validation="Restore succeeds; SARIF has no missing package/type findings; migrated project opens and validates in Studio.",
                evidence=format_examples(missing_package_examples + type_missing_examples),
            )
        )

    if type_missing_examples and not missing_package_examples:
        risks.append(
            risk_item(
                severity="Blocker",
                location="SARIF type resolution findings",
                component="Custom or unavailable activity types",
                failure_mode="Workflows cannot compile until all activity classes can be resolved in Windows.",
                replacement="Windows-compatible package version or redesigned workflow logic.",
                resolution="Map each missing class/namespace to a package or custom library. If source is available, migrate and republish the custom activity package before process upgrade; if source is unavailable, obtain a vendor/client Windows-compatible package or replace the activity behavior with supported activities/API/coded workflow logic, then rerun analysis.",
                owner="Client Owner + Human + Coding Agent",
                automation="Partial: agent can inspect XAML namespaces, propose replacements, and update references; human/client must provide package source, API contracts, or replacement decisions.",
                validation="No TYPE-MISSING findings; project validates/builds.",
                evidence=format_examples(type_missing_examples),
            )
        )

    expression_examples = matching_fragments(
        project_path,
        [re.compile(r"=\s*[\"']\[\s*\{\s*\}\s*\][\"']"), re.compile(r">\s*\[\s*\{\s*\}\s*\]\s*<")],
    )
    expression_examples.extend(
        sarif_examples(
            classified,
            lambda item: "BC36914" in item["message"]
            or "BC36915" in item["message"]
            or "{}" in item["message"],
        )
    )
    if expression_examples:
        risks.append(
            risk_item(
                severity="Blocker",
                location=format_examples(expression_examples),
                component="Ambiguous VB array initializer `{}`",
                failure_mode="Windows validation can fail because stricter type inference cannot infer the array element type.",
                replacement="Use a typed initializer such as `New Object() {}` or explicit typed values matching the target property.",
                resolution="Replace `[{}]` with a typed initializer such as `[New Object() {}]` only when the target property accepts an object array; otherwise inspect the activity property and provide explicit typed values that match the expected row or argument shape.",
                owner="Coding Agent",
                automation="High: the coding agent can locate and update deterministic expression patterns, then verify property type/schema and rerun validation.",
                validation="No BC36914/BC36915 or ST-PMG-002 equivalent findings; Windows validation/build passes.",
                evidence=format_examples(expression_examples),
            )
        )

    save_image_examples = activity_examples(records, {"SaveImage", "Save Image"})
    save_image_examples.extend(
        sarif_examples(
            classified,
            lambda item: "SAVEIMAGE" in item["message"].upper()
            or "MIGRATIONNOTIMPLEMENTED" in item["message"].upper(),
        )
    )
    if save_image_examples:
        risks.append(
            risk_item(
                severity="Blocker",
                location=format_examples(save_image_examples),
                component="Classic `SaveImage` activity",
                failure_mode="Workflow Migrator may not implement this conversion, leaving screenshot persistence unresolved.",
                replacement="Windows-compatible screenshot/file persistence helper or supported image/file activities.",
                resolution="Replace the unsupported save step with a Windows-compatible helper that writes the captured image to the expected file path, preserve downstream upload/use activities, and validate file creation in the target robot session.",
                owner="Coding Agent + Human",
                automation="Partial: agent can add or refactor deterministic file/image save logic; human must validate screenshot capture, permissions, and downstream upload/use behavior in the target robot session.",
                validation="No migration-not-implemented finding; screenshot file is created and consumed successfully at runtime.",
                evidence=format_examples(save_image_examples),
            )
        )

    classic_uia_names = {
        "AttachBrowser",
        "AttachWindow",
        "Check",
        "Click",
        "ClickText",
        "ElementExists",
        "FindElement",
        "GetAttribute",
        "GetFullText",
        "GetText",
        "GetValue",
        "GetVisibleText",
        "Highlight",
        "Hover",
        "OpenBrowser",
        "SelectItem",
        "SetText",
        "TakeScreenshot",
        "TypeInto",
        "UiElementExists",
    }
    classic_uia_examples = activity_examples(records, classic_uia_names)
    if classic_uia_examples or has_dependency(project_path, "UiPath.UIAutomation.Activities"):
        risks.append(
            risk_item(
                severity="High",
                location=format_examples(classic_uia_examples) if classic_uia_examples else "UiPath.UIAutomation.Activities dependency",
                component="Classic UI Automation activities",
                failure_mode="Supported activities may migrate, but selectors, application scopes, null input element behavior, and runtime timing can change.",
                replacement="Use modern UI Automation activities under stable `Use Application/Browser` scopes and Object Repository targets where appropriate.",
                resolution="Run Workflow Migrator with the UIA extension enabled, inspect each generated `Use Application/Browser` scope and annotations, recapture unstable selectors, replace fragile classic patterns where needed, and smoke-test representative application flows.",
                owner="Workflow Migrator + Human + Coding Agent",
                automation="Partial: Workflow Migrator handles supported conversions; agent can inspect generated scopes and repair obvious selector/scope structure; humans must validate UI behavior against the real applications.",
                validation="ST-AMG-001/post-migration annotations reviewed; selectors and application smoke tests pass.",
                evidence=format_examples(classic_uia_examples),
            )
        )

    image_uia_names = {"ClickImage", "ClickOCRText", "FindImage", "ImageExists", "WaitImageAppear", "WaitImageVanish"}
    image_uia_examples = activity_examples(records, image_uia_names)
    if image_uia_examples:
        risks.append(
            risk_item(
                severity="High",
                location=format_examples(image_uia_examples),
                component="Image/OCR-based UI Automation",
                failure_mode="Image and OCR actions are sensitive to resolution, themes, OCR engine scope, and generated modern application scopes.",
                replacement="Prefer selector-based modern UIA activities; keep OCR/image only where no stable selector exists.",
                resolution="Review each image/OCR activity, determine whether a stable selector or accessible attribute exists, replace with selector-based modern UIA where possible, and validate remaining image/OCR steps under the target resolution/theme/OCR engine.",
                owner="Coding Agent + Human",
                automation="Partial: agent can identify and replace obvious cases; human must validate against the real application UI.",
                validation="No unexpected image/OCR migration warnings; target UI flow passes at runtime.",
                evidence=format_examples(image_uia_examples),
            )
        )

    productivity_examples = matching_fragments(
        project_path,
        [
            re.compile(r"GSuite|Google|Office365|Microsoft365", re.IGNORECASE),
            re.compile(r"UseConnectionService|ConnectionId|ServiceAccount|KeyPath", re.IGNORECASE),
        ],
    )
    if productivity_examples or has_dependency(
        project_path,
        "UiPath.GSuite.Activities",
        "UiPath.MicrosoftOffice365.Activities",
    ):
        risks.append(
            risk_item(
                severity="High",
                location=format_examples(productivity_examples) if productivity_examples else "Productivity activity dependency",
                component="GSuite/Microsoft 365 productivity connections",
                failure_mode="Migrated productivity activities may require Orchestrator connection IDs; local service-account keys and legacy auth can fail in the target environment.",
                replacement="Provision Orchestrator connections and pass Workflow Migrator a `--config=<connection.json>` mapping for required `ConnectionId` values.",
                resolution="Inventory every GSuite/Microsoft 365 scope/activity, provision the required Integration Service or Orchestrator connection IDs, prepare the CLI connection config JSON, remove or secure local key-file references, and test read/write/upload/send operations.",
                owner="Client Owner + Human + Coding Agent",
                automation="Partial: agent can generate config templates and update references; client/human must provision connections and validate permissions.",
                validation="Migrated project uses expected ConnectionId values; read/write/upload/send operations pass with non-production data.",
                evidence=format_examples(productivity_examples),
            )
        )

    smtp_examples = matching_fragments(
        project_path,
        [
            re.compile(r"SMTP|SendSMTP|Smtp", re.IGNORECASE),
            re.compile(r"\b(Server|Port|From)=['\"]", re.IGNORECASE),
        ],
    )
    if smtp_examples or has_dependency(project_path, "UiPath.Mail.Activities"):
        risks.append(
            risk_item(
                severity="Medium",
                location=format_examples(smtp_examples) if smtp_examples else "UiPath.Mail.Activities dependency",
                component="SMTP/Mail activities and hardcoded mail settings",
                failure_mode="Notifications can fail if relay, sender, authentication, package behavior, or network access changes in Windows runtime.",
                replacement="Use Microsoft 365 connection activities when appropriate, or externalize SMTP relay settings into assets/configuration.",
                resolution="Decide whether the target runtime should use SMTP relay or Microsoft 365 connection activities, provision the approved relay/connection, move server/sender/port/recipient values to config or assets, and send success/failure test notifications.",
                owner="Client Owner + Coding Agent",
                automation="Partial: agent can refactor hardcoded values; client/human must approve relay/M365 connection strategy.",
                validation="Success and failure notification smoke tests pass from the target robot environment.",
                evidence=format_examples(smtp_examples),
            )
        )

    hardcoded_examples = matching_fragments(
        project_path,
        [
            re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),
            re.compile(r"[A-Za-z]:\\[^\"']+"),
            re.compile(r"https?://[^\"'\s<>]+"),
            re.compile(r"\b(Server|Host|UserEmail|KeyPath|FolderId|FileId)=['\"][^'\"]+['\"]", re.IGNORECASE),
        ],
        limit=20,
    )
    if hardcoded_examples:
        risks.append(
            risk_item(
                severity="Medium",
                location=format_examples(hardcoded_examples),
                component="Hardcoded configuration values",
                failure_mode="Environment-specific paths, URLs, email addresses, IDs, or key paths may break after migration or expose secrets/configuration in source.",
                replacement="Use Orchestrator assets, Config.xlsx, environment-specific settings, or secure credential stores.",
                resolution="Classify each hardcoded value as environment configuration, identifier, path, endpoint, or secret; externalize it to Config.xlsx, Orchestrator assets, or credential storage; mask/rotate sensitive values where needed; then run with target-environment values.",
                owner="Coding Agent + Human",
                automation="Partial: agent can identify and externalize obvious constants; human/client must confirm correct target values.",
                validation="No target-environment constants remain in source; migrated run uses approved assets/configuration.",
                evidence=format_examples(hardcoded_examples),
            )
        )

    soap_examples = matching_fragments(project_path, [re.compile(r"SOAP|WebService|ServiceReference", re.IGNORECASE)])
    if soap_examples:
        risks.append(
            risk_item(
                severity="High",
                location=format_examples(soap_examples),
                component="SOAP/web service integration",
                failure_mode="SOAP web services are not supported in Windows and cross-platform projects.",
                replacement="Replace with HTTP/REST calls, supported libraries, or a coded workflow/client compatible with the target runtime.",
                resolution="Inventory each SOAP/service-reference call, obtain the service contract and test endpoint, choose a supported REST/HTTP/client-library or coded workflow replacement, refactor the call, and run integration tests before production migration.",
                owner="Client Owner + Coding Agent",
                automation="Partial: agent can refactor once API contract is known; client/human must provide service contract and test access.",
                validation="Replacement service calls pass integration tests in the target environment.",
                evidence=format_examples(soap_examples),
            )
        )

    return risks


def assign_risk_ids(risks: list[dict[str, str]]) -> list[dict[str, str]]:
    for index, risk in enumerate(risks, start=1):
        risk["id"] = f"R-{index:03d}"
    return risks


def risk_status(risks: list[dict[str, str]], fallback_status: str) -> str:
    if any(risk["severity"] == "Blocker" for risk in risks):
        return "Blocked"
    if any(risk["severity"] == "High" for risk in risks):
        return "High Risk"
    if any(risk["severity"] == "Medium" for risk in risks):
        return "Ready With Warnings"
    return fallback_status


def recommended_migration_path(risks: list[dict[str, str]]) -> str:
    if any(risk["severity"] == "Blocker" for risk in risks):
        return "Resolve blockers first, then run a Workflow Migrator pilot on a project copy."
    if any("Classic UI Automation" in risk["component"] for risk in risks):
        return "Run a Workflow Migrator pilot on a project copy, then validate selectors and generated application scopes."
    return "Proceed with a consent-gated Workflow Migrator pilot on a project copy, followed by Studio validation."


def has_restore_blocker(sarif: dict[str, Any] | None) -> bool:
    _, findings = summarize_sarif(sarif)
    classified = classify_findings(findings)
    return any(
        item["category"] == "Blocking Issues"
        and (
            "RESTORE-MISSING-PACKAGE" in item["rule_id"].upper()
            or ("package" in item["message"].lower() and "not found" in item["message"].lower())
            or "not available from the configured package feeds" in item["plain_language"]
        )
        for item in classified
    )


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


def cli_option_value(args: list[str], *names: str) -> str:
    for index, arg in enumerate(args):
        for name in names:
            if arg == name:
                return args[index + 1] if index + 1 < len(args) else "(provided without value)"
            if arg.startswith(f"{name}="):
                return arg.split("=", 1)[1]
    return ""


def studio_compatibility_action(target_studio_version: str | None) -> str:
    target = (target_studio_version or "").strip()
    normalized = target.lower()
    if not target:
        return "Target Studio version was not specified. Treat package versions as unverified until the migrated project is opened/analyzed in the Studio version that will own it."
    if "sts" in normalized or "latest" in normalized:
        return "Latest STS no longer creates or edits Windows-Legacy source projects. Use the CLI/LTS-compatible conversion path for the legacy source, then open and validate the converted Windows project in the target STS Studio."
    if normalized.startswith("2024.10") or normalized.startswith("24.10"):
        return "Validate the converted project in Studio 2024.10 and keep package versions available from the 2024.10-approved feeds/governance policy."
    if normalized.startswith("2025.10") or normalized.startswith("25.10"):
        return "Validate the converted project in Studio 2025.10 and keep package versions available from the 2025.10-approved feeds/governance policy."
    return "Validate the converted project in the named Studio release and pin or approve package versions through that environment's feeds/governance policy."


def package_version_rows(
    *,
    target_studio_version: str | None,
    passthrough_args: list[str],
) -> list[list[str]]:
    outlook_version = cli_option_value(passthrough_args, "--outlook-package-version")
    return [
        [
            "Target Studio version",
            target_studio_version.strip() if target_studio_version else "Not specified",
            studio_compatibility_action(target_studio_version),
        ],
        [
            "General dependency version rule",
            "Studio/CLI package resolution through configured feeds",
            "If the same package version exists in configured package sources, keep it. If not, select the highest patch of the nearest available version; unresolved packages remain blockers.",
        ],
        [
            "Workflow Migrator control",
            "Pipeline plus configured package feeds",
            "The helper records and reports package decisions; it does not choose arbitrary package versions outside the CLI, extensions, Studio package sources, Orchestrator feeds, and any caller-provided CLI options.",
        ],
        [
            "Mail/Microsoft 365 package override",
            f"`--outlook-package-version {outlook_version}`" if outlook_version else "`--outlook-package-version` not supplied",
            "When supplied, the CLI uses this Microsoft Office 365 activities package version for supported mail migration. When omitted, the bundled CLI README documents default `3.1.21`; confirm that version is approved for the target Studio release or pass an explicit compatible version.",
        ],
        [
            "Compatibility validation",
            "Required before approval",
            "Open/build/analyze the migrated output in the target Studio version and verify each selected package restores from the same feeds the robot/developer will use.",
        ],
    ]


def add_action_guidance(lines: list[str], risks: list[dict[str, str]]) -> None:
    lines.extend(["", "## How to Address Findings", ""])
    if not risks:
        lines.append("- No specific remediation findings were detected. Still validate the migrated project in Studio and run representative workflow tests.")
        return

    for risk in risks:
        lines.extend(
            [
                f"### {risk['id']} - {risk['component']}",
                "",
                f"- **Primary owner:** {risk['owner']}",
                f"- **Coding agent can assist with:** {risk['automation']}",
                f"- **Human/client decision needed:** Confirm business behavior, package/feed ownership, credentials, environment values, selectors, or replacement strategy where the finding depends on external systems or business process knowledge.",
                f"- **Fix approach:** {risk['resolution']}",
                f"- **Preferred replacement:** {risk['replacement']}",
                f"- **Validation:** {risk['validation']}",
                "",
            ]
        )


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
    deep_analyze_exit_code: int | None = None,
    deep_sarif_path: Path | None = None,
    deep_sarif: dict[str, Any] | None = None,
    include_raw_analyzer_output: bool = False,
    include_migration_gate: bool = False,
    target_studio_version: str | None = None,
    passthrough_args: list[str] | None = None,
) -> Path:
    counts, findings = summarize_sarif(sarif)
    deep_counts, deep_findings = summarize_sarif(deep_sarif)
    classified = classify_findings(dedupe_findings(findings + deep_findings))
    base_status = readiness_status(analyze_exit_code, classified, sarif_path)
    risks = assign_risk_ids(build_assessment_risks(project_path, classified))
    status = risk_status(risks, base_status)
    blocking_risks = [risk for risk in risks if risk["severity"] == "Blocker"]
    high_risks = [risk for risk in risks if risk["severity"] == "High"]
    medium_risks = [risk for risk in risks if risk["severity"] == "Medium"]
    automated = [item for item in classified if item["category"] == "Automated Changes Detected"]
    project_attention = custom_dependency_items(project_path) + custom_namespace_items(project_path)
    dependencies = project_dependencies(project_path)
    report_path.parent.mkdir(parents=True, exist_ok=True)

    lines = [
        "# Windows - Legacy to Windows Migration Risk Report",
        "",
        "## Executive Summary",
        "",
        f"- **Project:** `{project_name(project_path)}`",
        f"- **Current compatibility:** `{project_target_framework(project_path)}`",
        "- **Target compatibility:** Windows",
        f"- **Target Studio version for validation:** `{target_studio_version.strip() if target_studio_version else 'Not specified'}`",
        f"- **Overall migration status:** {status}",
        f"- **Primary blockers:** {len(blocking_risks)}",
        f"- **High-risk items:** {len(high_risks)}",
        f"- **Medium-risk items:** {len(medium_risks)}",
        f"- **Automated changes detected:** {len(automated)}",
        f"- **Recommended migration path:** {recommended_migration_path(risks)}",
        "",
        "## Pre-Flight Status",
        "",
    ]

    add_table(
        lines,
        ["Check", "Result", "Evidence"],
        [
            ["Project path exists", "Yes", str(project_path)],
            ["Analysis-only workflow used", "Yes", "The helper ran `analyze`; `upgrade` remains blocked by the migration gate until explicit approval."],
            ["Original project write migration performed", "No", "No `upgrade` command is run during the analysis phase."],
            ["Planned output path recorded", "Yes", str(output_path or default_output_path(project_path))],
        ],
    )

    lines.extend(["", "## Validation Evidence", ""])
    evidence_rows = [
        [
            "Workflow Migrator analysis",
            "Pass" if analyze_exit_code == 0 else "Fail",
            f"`analyze` exit code `{analyze_exit_code}`; SARIF `{sarif_path}`" if sarif_path else f"`analyze` exit code `{analyze_exit_code}`; SARIF not found",
        ]
    ]
    if deep_analyze_exit_code is not None:
        evidence_rows.append(
            [
                "Workflow Migrator analysis with missing dependencies ignored",
                "Pass" if deep_analyze_exit_code == 0 else "Fail",
                f"`analyze --ignore-missing-dependencies` exit code `{deep_analyze_exit_code}`; SARIF `{deep_sarif_path}`"
                if deep_sarif_path
                else f"`analyze --ignore-missing-dependencies` exit code `{deep_analyze_exit_code}`; SARIF not found",
            ]
        )
    else:
        evidence_rows.append(
            [
                "Workflow Migrator analysis with missing dependencies ignored",
                "Not run",
                "No restore blocker was detected, or the option was already provided by the caller.",
            ]
        )
    evidence_rows.extend(
        [
            [
                "Dependencies reviewed",
                "Yes" if dependencies else "No",
                ", ".join(f"{name} {version}" for name, version in sorted(dependencies.items())) or "No project.json dependencies parsed.",
            ],
            [
                "Custom packages/namespaces reviewed",
                "Yes" if project_attention else "No custom packages or namespaces found",
                format_examples([f"{item['item']}" for item in project_attention]),
            ],
        ]
    )
    add_table(lines, ["Check", "Result", "Evidence"], evidence_rows)

    lines.extend(["", "## Package Version Selection and Studio Compatibility", ""])
    add_table(
        lines,
        ["Decision point", "Observed/selected value", "Guidance"],
        package_version_rows(
            target_studio_version=target_studio_version,
            passthrough_args=passthrough_args or [],
        ),
    )

    lines.extend(
        [
            "",
            "## Migration Risks and Limitations",
            "",
            "- Analyzer findings are combined with project and XAML inspection so the report calls out likely runtime risks, not only SARIF rule counts.",
            "- The assessment cannot prove runtime business equivalence; selectors, credentials, Orchestrator assets, queues, connection names, file paths, and external services still require validation.",
            "- Custom and third-party activity packages require owner review because Windows compatibility depends on package implementation and available feeds.",
            "- GSuite, Microsoft 365, SMTP, UI Automation, image/OCR, PDF, Excel, SOAP, and hardcoded configuration patterns require targeted post-migration testing.",
            "- A clean analysis report does not replace opening/building the migrated project in Studio and running representative workflow tests.",
            "",
            "## Migration Risks",
            "",
        ]
    )

    if risks:
        add_table(
            lines,
            [
                "ID",
                "Severity",
                "Location",
                "Problematic component",
                "Evidence",
                "Failure mode",
                "Recommended replacement",
                "Resolution steps",
                "Owner",
                "Automation eligibility",
                "Validation",
            ],
            [
                [
                    risk["id"],
                    risk["severity"],
                    risk["location"],
                    risk["component"],
                    risk["evidence"],
                    risk["failure_mode"],
                    risk["replacement"],
                    risk["resolution"],
                    risk["owner"],
                    risk["automation"],
                    risk["validation"],
                ]
                for risk in risks
            ],
        )
    else:
        lines.append("- No known migration risk patterns were found beyond normal validation requirements.")

    lines.extend(["", "## Blockers", ""])

    if blocking_risks:
        for risk in blocking_risks:
            lines.extend(
                [
                    f"### {risk['id']} - {risk['component']}",
                    "",
                    f"- **Where:** {risk['location']}",
                    f"- **Evidence:** {risk['evidence']}",
                    f"- **Why it blocks migration:** {risk['failure_mode']}",
                    f"- **Replacement:** {risk['replacement']}",
                    f"- **Fix steps:** {risk['resolution']}",
                    f"- **Owner:** {risk['owner']}",
                    f"- **Can be automated:** {risk['automation']}",
                    f"- **Validation:** {risk['validation']}",
                    "",
                ]
            )
    else:
        lines.append("- None found.")

    add_action_guidance(lines, risks)

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

    lines.extend(["", "## Resolution Order", ""])
    resolution_rows = [
        ["1", "Preserve backup/source-control checkpoint and work on a copy", "All", "Coding Agent", "Backup/copy recorded before upgrade"],
        ["2", "Resolve dependency/feed/library blockers", format_examples([risk["id"] for risk in risks if "package" in risk["component"].lower() or "activity types" in risk["component"].lower()]), "Client Owner + Human + Coding Agent", "Restore and type-resolution findings are clean"],
        ["3", "Fix deterministic compile or migration blockers before upgrade", format_examples([risk["id"] for risk in blocking_risks if "array" in risk["component"].lower() or "saveimage" in risk["component"].lower()]), "Coding Agent", "No known expression or migration-not-implemented blocker remains"],
        ["4", "Prepare connection/configuration strategy", format_examples([risk["id"] for risk in risks if "connection" in risk["component"].lower() or "smtp" in risk["component"].lower() or "hardcoded" in risk["component"].lower()]), "Client Owner + Human + Coding Agent", "Connection IDs, relay decisions, and config/assets are documented"],
        ["5", "Run Workflow Migrator pilot on a copy after approval", "All", "Workflow Migrator", "SARIF reviewed and no blockers remain"],
        ["6", "Fix converted validation/build issues", "All", "Coding Agent", "Windows project validates/builds"],
        ["7", "Validate UI scopes, selectors, connections, and business outcomes", "All", "Human + Coding Agent", "Representative smoke/regression tests pass"],
    ]
    add_table(lines, ["Order", "Action", "Risk IDs", "Owner", "Exit criteria"], resolution_rows)

    lines.extend(
        [
            "",
            "## Final Recommendation",
            "",
            approval_recommendation(status),
            recommended_migration_path(risks),
            "",
            "## Official Guidance Used",
            "",
            "- UiPath Windows - Legacy compatibility guidance recommends inventorying projects, libraries, and dependencies; migrating libraries first; piloting conversion; validating external systems; and addressing known expression compatibility issues such as `{}` to `new Object() {}`.",
            "- UiPath Windows - Legacy dependency guidance states that conversion keeps the same package version when it exists in configured package sources, otherwise selects the highest patch of the nearest available version; unresolved dependencies remain migration blockers.",
            "- UiPath latest STS guidance states that STS no longer supports creating or editing Windows-Legacy source projects; validate converted Windows projects in STS only after conversion through a compatible path.",
            "- UiPath Workflow Migrator guidance recommends running `analyze` before `upgrade`, reviewing SARIF from the `.upgrade` folder, using `--config=<connection.json>` for productivity activity `ConnectionId` values, and validating generated UI Automation application scopes.",
            "- UiPath Workflow Migrator guidance documents supported and unsupported UI Automation and Mail activity migrations; supported migrations can still require runtime validation.",
            "",
            "## Finding Counts",
            "",
        ]
    )

    if counts:
        for level in ["error", "warning", "note", "none"]:
            lines.append(f"- primary {level}: {counts.get(level, 0)}")
    else:
        lines.append("- No primary SARIF findings were parsed.")
    if deep_analyze_exit_code is not None:
        if deep_counts:
            for level in ["error", "warning", "note", "none"]:
                lines.append(f"- ignore-missing-dependencies {level}: {deep_counts.get(level, 0)}")
        else:
            lines.append("- No ignore-missing-dependencies SARIF findings were parsed.")

    lines.extend(
        [
            "",
            "## Analysis Context",
            "",
            f"- Generated UTC: {datetime.now(timezone.utc).isoformat()}",
            f"- Project path: `{project_path}`",
            f"- Planned output path: `{output_path or default_output_path(project_path)}`",
            f"- Workflow Migrator CLI: `{cli}`",
            f"- Primary SARIF source: `{sarif_path}`" if sarif_path else "- Primary SARIF source: not found",
            f"- Ignore-missing-dependencies SARIF source: `{deep_sarif_path}`" if deep_sarif_path else "- Ignore-missing-dependencies SARIF source: not run or not found",
        ]
    )

    if include_raw_analyzer_output:
        lines.extend(["", "## Raw Analyzer Output", ""])

        if classified:
            for item in classified:
                location = f" ({item['location']})" if item["location"] else ""
                lines.append(
                    f"- [{item['level']}] `{item['rule_id']}`{location}: {item['message']}"
                )
        else:
            lines.append("- No analyzer findings to list.")

    if include_migration_gate:
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

    deep_analyze_exit_code: int | None = None
    deep_sarif_path: Path | None = None
    deep_sarif: dict[str, Any] | None = None
    if has_restore_blocker(sarif) and not has_cli_option(passthrough, "--ignore-missing-dependencies"):
        deep_analyze_args = [*analyze_args, "--ignore-missing-dependencies"]
        deep_analyze_exit_code = run_cli(
            cli,
            deep_analyze_args,
            status_mode=args.status_mode,
            poll_interval_seconds=args.poll_interval_seconds,
            operation_name="migration analysis with missing dependencies ignored",
        )
        deep_sarif_path = find_latest_sarif(project_path)
        if deep_sarif_path == sarif_path:
            deep_sarif_path = None
        deep_sarif = load_sarif(deep_sarif_path)

    report = write_analysis_report(
        report_path,
        project_path=project_path,
        output_path=resolved_output_path,
        cli=cli,
        analyze_exit_code=analyze_exit_code,
        sarif_path=sarif_path,
        sarif=sarif,
        deep_analyze_exit_code=deep_analyze_exit_code,
        deep_sarif_path=deep_sarif_path,
        deep_sarif=deep_sarif,
        include_raw_analyzer_output=args.include_raw_analyzer_output,
        include_migration_gate=args.include_migration_gate,
        target_studio_version=args.target_studio_version,
        passthrough_args=passthrough,
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
    parser.add_argument(
        "--include-raw-analyzer-output",
        action="store_true",
        help="Include the raw SARIF/analyzer finding list in the Markdown analysis report.",
    )
    parser.add_argument(
        "--include-migration-gate",
        action="store_true",
        help="Include the consent reminder section in the Markdown analysis report.",
    )
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
    parser.add_argument(
        "--target-studio-version",
        help="Studio version that will open/validate the migrated Windows project, for example 2024.10, 2025.10, or latest STS.",
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
