param(
    [string]$Cli,
    [string]$ToolRoot,
    [switch]$Locate,
    [switch]$ConsentGated,
    [string]$ProjectPath,
    [string]$OutputPath,
    [string]$ReportPath,
    [switch]$IncludeRawAnalyzerOutput,
    [switch]$IncludeMigrationGate,
    [switch]$ApproveMigration,
    [ValidateSet("wait", "poll")]
    [string]$StatusMode = "wait",
    [double]$PollIntervalSeconds = 60,
    [switch]$SkipRemediation,
    [string]$TargetStudioVersion,
    [switch]$CliVerbose,
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$CliArgs = @()
)

$ErrorActionPreference = "Stop"

$CliExeName = "UiPath.Upgrade.exe"
$CliDllName = "UiPath.Upgrade.dll"
$DefaultToolDir = "tools\uipath-upgrade-cli"
$StopForConsentExitCode = 3

function Get-SkillRoot {
    return (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
}

function Get-DefaultToolRoot {
    return Join-Path (Get-SkillRoot) $DefaultToolDir
}

function Resolve-Cli {
    if ($Cli) {
        $candidate = Resolve-Path -LiteralPath $Cli -ErrorAction SilentlyContinue
        if ($candidate) {
            return $candidate.Path
        }
    }

    if ($env:UIPATH_UPGRADE_CLI) {
        $candidate = Resolve-Path -LiteralPath $env:UIPATH_UPGRADE_CLI -ErrorAction SilentlyContinue
        if ($candidate) {
            return $candidate.Path
        }
    }

    $root = if ($ToolRoot) { $ToolRoot } else { Get-DefaultToolRoot }
    if (-not (Test-Path -LiteralPath $root)) {
        return $null
    }

    foreach ($name in @($CliExeName, $CliDllName)) {
        $direct = Join-Path $root $name
        if (Test-Path -LiteralPath $direct -PathType Leaf) {
            return (Resolve-Path -LiteralPath $direct).Path
        }
    }

    # Use an explicit name filter; -Include with -LiteralPath can pass unrelated files.
    foreach ($name in @($CliExeName, $CliDllName)) {
        $nested = Get-ChildItem -LiteralPath $root -Recurse -File -ErrorAction SilentlyContinue |
            Where-Object { $_.Name -eq $name } |
            Select-Object -First 1
        if ($nested) {
            return $nested.FullName
        }
    }

    return $null
}

function Test-CliOption {
    param([string[]]$Args, [string[]]$Names)
    foreach ($arg in $Args) {
        foreach ($name in $Names) {
            if ($arg -eq $name -or $arg.StartsWith("$name=")) {
                return $true
            }
        }
    }
    return $false
}

function Get-CliOptionValue {
    param([string[]]$Args, [string[]]$Names)
    for ($index = 0; $index -lt $Args.Count; $index++) {
        $arg = $Args[$index]
        foreach ($name in $Names) {
            if ($arg -eq $name) {
                if ($index + 1 -lt $Args.Count) {
                    return $Args[$index + 1]
                }
                return "(provided without value)"
            }
            $prefix = $name + "="
            if ($arg.StartsWith($prefix)) {
                return $arg.Substring($prefix.Length)
            }
        }
    }
    return ""
}

function Get-StudioCompatibilityAction {
    param([string]$Target)
    $value = if ($Target) { $Target.Trim() } else { "" }
    $normalized = $value.ToLowerInvariant()
    if (-not $value) {
        return "Target Studio version was not specified. Treat package versions as unverified until the migrated project is opened/analyzed in the Studio version that will own it."
    }
    if ($normalized.Contains("sts") -or $normalized.Contains("latest")) {
        return "Latest STS no longer creates or edits Windows-Legacy source projects. Use the CLI/LTS-compatible conversion path for the legacy source, then open and validate the converted Windows project in the target STS Studio."
    }
    if ($normalized.StartsWith("2024.10") -or $normalized.StartsWith("24.10")) {
        return "Validate the converted project in Studio 2024.10 and keep package versions available from the 2024.10-approved feeds/governance policy."
    }
    if ($normalized.StartsWith("2025.10") -or $normalized.StartsWith("25.10")) {
        return "Validate the converted project in Studio 2025.10 and keep package versions available from the 2025.10-approved feeds/governance policy."
    }
    return "Validate the converted project in the named Studio release and pin or approve package versions through that environment's feeds/governance policy."
}

function Get-PackageVersionRows {
    param([string]$Target, [string[]]$PassThroughArgs)
    $outlookVersion = Get-CliOptionValue $PassThroughArgs @("--outlook-package-version")
    $targetDisplay = if ($Target) { $Target.Trim() } else { "Not specified" }
    $outlookDisplay = if ($outlookVersion) { "--outlook-package-version $outlookVersion" } else { "--outlook-package-version not supplied" }
    return @(
        @("Target Studio version", $targetDisplay, (Get-StudioCompatibilityAction $Target)),
        @("General dependency version rule", "Studio/CLI package resolution through configured feeds", "If the same package version exists in configured package sources, keep it. If not, select the highest patch of the nearest available version; unresolved packages remain blockers."),
        @("Workflow Migrator control", "Pipeline plus configured package feeds", "The helper records and reports package decisions; it does not choose arbitrary package versions outside the CLI, extensions, Studio package sources, Orchestrator feeds, and any caller-provided CLI options."),
        @("Mail/Microsoft 365 package override", $outlookDisplay, "When supplied, the CLI uses this Microsoft Office 365 activities package version for supported mail migration. When omitted, the bundled CLI README documents default 3.1.21; confirm that version is approved for the target Studio release or pass an explicit compatible version."),
        @("Compatibility validation", "Required before approval", "Open/build/analyze the migrated output in the target Studio version and verify each selected package restores from the same feeds the robot/developer will use.")
    )
}

function Add-ActionGuidance {
    param([System.Collections.Generic.List[string]]$Lines, [object[]]$Risks)
    $Lines.Add("")
    $Lines.Add("## How to Address Findings")
    $Lines.Add("")
    if ($Risks.Count -eq 0) {
        $Lines.Add("- No specific remediation findings were detected. Still validate the migrated project in Studio and run representative workflow tests.")
        return
    }

    foreach ($risk in $Risks) {
        $Lines.Add("### $($risk.Id) - $($risk.Component)")
        $Lines.Add("")
        $Lines.Add("- **Primary owner:** $($risk.Owner)")
        $Lines.Add("- **Coding agent can assist with:** $($risk.Automation)")
        $Lines.Add("- **Human/client decision needed:** Confirm business behavior, package/feed ownership, credentials, environment values, selectors, or replacement strategy where the finding depends on external systems or business process knowledge.")
        $Lines.Add("- **Fix approach:** $($risk.Resolution)")
        $Lines.Add("- **Preferred replacement:** $($risk.Replacement)")
        $Lines.Add("- **Validation:** $($risk.Validation)")
        $Lines.Add("")
    }
}

function Invoke-UpgradeCli {
    param(
        [string]$CliPath,
        [string[]]$Arguments,
        [string]$OperationName = "UiPath.Upgrade.Cli"
    )

    if ($Arguments.Count -eq 0) {
        Write-Output $CliPath
        return 0
    }

    $fileName = $CliPath
    $argumentList = $Arguments
    if ([System.IO.Path]::GetExtension($CliPath).ToLowerInvariant() -eq ".dll") {
        $fileName = "dotnet"
        $argumentList = @($CliPath) + $Arguments
    }

    if ($StatusMode -eq "wait") {
        & $fileName @argumentList | ForEach-Object { Write-Host $_ }
        $exitCode = $LASTEXITCODE
        return $exitCode
    }

    $process = Start-Process -FilePath $fileName -ArgumentList $argumentList -NoNewWindow -PassThru
    $started = Get-Date
    while (-not $process.HasExited) {
        Start-Sleep -Seconds $PollIntervalSeconds
        $process.Refresh()
        if (-not $process.HasExited) {
            $elapsed = [int]((Get-Date) - $started).TotalSeconds
            Write-Host "$OperationName still running after ${elapsed}s; next status check in ${PollIntervalSeconds}s."
        }
    }
    return $process.ExitCode
}

function Get-LatestSarif {
    param([string]$Project)
    $upgradeDir = Join-Path $Project ".upgrade"
    if (-not (Test-Path -LiteralPath $upgradeDir)) {
        return $null
    }
    $latest = Get-ChildItem -LiteralPath $upgradeDir -Recurse -File -Filter "*.sarif" -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 1
    if ($latest) {
        return $latest.FullName
    }
    return $null
}

function Read-JsonFile {
    param([string]$Path)
    if (-not $Path -or -not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        return $null
    }
    try {
        return Get-Content -LiteralPath $Path -Raw -Encoding UTF8 | ConvertFrom-Json
    } catch {
        return $null
    }
}

function Get-ProjectJson {
    param([string]$Project)
    return Read-JsonFile (Join-Path $Project "project.json")
}

function Get-ProjectName {
    param([string]$Project)
    $projectJson = Get-ProjectJson $Project
    if ($projectJson -and $projectJson.name) {
        return [string]$projectJson.name
    }
    return Split-Path -Leaf $Project
}

function Get-ProjectTargetFramework {
    param([string]$Project)
    $projectJson = Get-ProjectJson $Project
    if ($projectJson -and $projectJson.targetFramework) {
        return [string]$projectJson.targetFramework
    }
    return "unknown"
}

function Get-ProjectDependencies {
    param([string]$Project)
    $projectJson = Get-ProjectJson $Project
    $items = @()
    if (-not $projectJson -or -not $projectJson.dependencies) {
        return $items
    }
    foreach ($property in $projectJson.dependencies.PSObject.Properties | Sort-Object Name) {
        $items += [pscustomobject]@{ Name = $property.Name; Version = [string]$property.Value }
    }
    return $items
}

function Get-XamlFiles {
    param([string]$Project)
    return Get-ChildItem -LiteralPath $Project -Recurse -File -Filter "*.xaml" -ErrorAction SilentlyContinue |
        Where-Object { $_.FullName -notmatch "[\\/]\.upgrade[\\/]" }
}

function Get-RelativeLocation {
    param([string]$Project, [string]$Path, [int]$LineNumber = 0)
    $base = [System.IO.Path]::GetFullPath($Project).TrimEnd([System.IO.Path]::DirectorySeparatorChar, [System.IO.Path]::AltDirectorySeparatorChar)
    $full = [System.IO.Path]::GetFullPath($Path)
    $relative = if ($full.StartsWith($base)) { $full.Substring($base.Length).TrimStart("\", "/") } else { $full }
    if ($LineNumber -gt 0) {
        return "${relative}:$LineNumber"
    }
    return $relative
}

function Format-Examples {
    param([string[]]$Values, [int]$Limit = 8)
    $unique = @()
    foreach ($value in $Values) {
        if (-not [string]::IsNullOrWhiteSpace($value) -and $unique -notcontains $value) {
            $unique += $value
        }
    }
    if ($unique.Count -eq 0) {
        return "-"
    }
    $suffix = if ($unique.Count -gt $Limit) { "; +$($unique.Count - $Limit) more" } else { "" }
    return (($unique | Select-Object -First $Limit) -join "; ") + $suffix
}

function Escape-Markdown {
    param([string]$Value)
    if ($null -eq $Value) {
        return ""
    }
    return (($Value -replace "\r?\n", " ") -replace "\s+", " ").Trim().Replace("|", "\|")
}

function Add-MarkdownTable {
    param(
        [System.Collections.Generic.List[string]]$Lines,
        [string[]]$Headers,
        [object[]]$Rows
    )
    $Lines.Add("| " + ($Headers -join " | ") + " |")
    $Lines.Add("| " + (($Headers | ForEach-Object { "---" }) -join " | ") + " |")

    $rowItems = @($Rows)
    if ($rowItems.Count -eq 0) {
        return
    }

    $normalizedRows = @()
    if ($rowItems[0] -is [System.Array] -and -not ($rowItems[0] -is [string])) {
        $normalizedRows = $rowItems
    } else {
        for ($index = 0; $index -lt $rowItems.Count; $index += $Headers.Count) {
            $last = [Math]::Min($index + $Headers.Count - 1, $rowItems.Count - 1)
            $normalizedRows += ,@($rowItems[$index..$last])
        }
    }

    foreach ($row in $normalizedRows) {
        $Lines.Add("| " + (($row | ForEach-Object { Escape-Markdown ([string]$_) }) -join " | ") + " |")
    }
}

function Get-SarifFindings {
    param([object]$Sarif)
    $findings = @()
    if (-not $Sarif -or -not $Sarif.runs) {
        return $findings
    }
    foreach ($run in $Sarif.runs) {
        foreach ($result in @($run.results)) {
            $level = if ($result.level) { [string]$result.level } else { "none" }
            $ruleId = if ($result.ruleId) { [string]$result.ruleId } elseif ($result.rule -and $result.rule.id) { [string]$result.rule.id } else { "unknown" }
            $message = if ($result.message.text) { [string]$result.message.text } elseif ($result.message.markdown) { [string]$result.message.markdown } else { "" }
            $location = ""
            if ($result.locations -and $result.locations.Count -gt 0) {
                $physical = $result.locations[0].physicalLocation
                $artifact = if ($physical.artifactLocation.uri) { [string]$physical.artifactLocation.uri } else { "" }
                $line = if ($physical.region.startLine) { [string]$physical.region.startLine } else { "" }
                $location = if ($artifact -and $line) { "${artifact}:$line" } else { $artifact }
            }
            $findings += [pscustomobject]@{
                Level = $level
                RuleId = $ruleId
                Message = (($message -replace "\r?\n", " ") -replace "\s+", " ").Trim()
                Location = $location
            }
        }
    }
    return $findings
}

function Test-RestoreBlocker {
    param([object[]]$Findings)
    foreach ($finding in $Findings) {
        $rule = $finding.RuleId.ToUpperInvariant()
        $message = $finding.Message.ToLowerInvariant()
        if ($rule.Contains("RESTORE-MISSING-PACKAGE") -or ($message.Contains("package") -and $message.Contains("not found"))) {
            return $true
        }
    }
    return $false
}

function New-Risk {
    param(
        [string]$Severity,
        [string]$Location,
        [string]$Component,
        [string]$Evidence,
        [string]$FailureMode,
        [string]$Replacement,
        [string]$Resolution,
        [string]$Owner,
        [string]$Automation,
        [string]$Validation
    )
    return [pscustomobject]@{
        Severity = $Severity
        Location = $Location
        Component = $Component
        Evidence = $Evidence
        FailureMode = $FailureMode
        Replacement = $Replacement
        Resolution = $Resolution
        Owner = $Owner
        Automation = $Automation
        Validation = $Validation
    }
}

function Get-XamlMatches {
    param([string]$Project, [string[]]$Patterns, [int]$Limit = 25)
    $results = @()
    foreach ($file in Get-XamlFiles $Project) {
        $lines = Get-Content -LiteralPath $file.FullName -Encoding UTF8 -ErrorAction SilentlyContinue
        for ($index = 0; $index -lt $lines.Count; $index++) {
            foreach ($pattern in $Patterns) {
                if ($lines[$index] -match $pattern) {
                    $snippet = (($lines[$index] -replace "\s+", " ").Trim())
                    $results += "$(Get-RelativeLocation $Project $file.FullName ($index + 1)) $snippet"
                    if ($results.Count -ge $Limit) {
                        return $results
                    }
                    break
                }
            }
        }
    }
    return $results
}

function Get-ActivityExamples {
    param([string]$Project, [string[]]$ActivityNames, [int]$Limit = 8)
    $examples = @()
    $namePattern = ($ActivityNames | ForEach-Object { [regex]::Escape($_) }) -join "|"
    $tagPattern = "<[^>]*:($namePattern)\b|<($namePattern)\b"
    foreach ($file in Get-XamlFiles $Project) {
        $lines = Get-Content -LiteralPath $file.FullName -Encoding UTF8 -ErrorAction SilentlyContinue
        for ($index = 0; $index -lt $lines.Count; $index++) {
            if ($lines[$index] -match $tagPattern) {
                $className = if ($Matches[1]) { $Matches[1] } else { $Matches[2] }
                $displayName = $className
                $window = ($lines[$index..([Math]::Min($index + 3, $lines.Count - 1))] -join " ")
                if ($window -match 'DisplayName=[''"]([^''"]+)[''"]') {
                    $displayName = [System.Net.WebUtility]::HtmlDecode($Matches[1])
                }
                $examples += "{0} ``{1}`` ({2})" -f (Get-RelativeLocation $Project $file.FullName ($index + 1)), $displayName, $className
                if ($examples.Count -ge $Limit) {
                    return $examples
                }
            }
        }
    }
    return $examples
}

function Get-AssessmentRisks {
    param([string]$Project, [object[]]$Findings)
    $risks = @()
    $dependencies = Get-ProjectDependencies $Project
    $customDependencies = @($dependencies | Where-Object { -not $_.Name.ToLowerInvariant().StartsWith("uipath.") -and $_.Name.ToLowerInvariant() -ne "newtonsoft.json" } | ForEach-Object { "$($_.Name) $($_.Version)" })
    $missingPackageFindings = @($Findings | Where-Object {
        $_.RuleId.ToUpperInvariant().Contains("RESTORE-MISSING-PACKAGE") -or ($_.Message.ToLowerInvariant().Contains("package") -and $_.Message.ToLowerInvariant().Contains("not found"))
    } | ForEach-Object { "{0} ``{1}`` {2}" -f $_.Location, $_.RuleId, $_.Message })
    $typeMissingFindings = @($Findings | Where-Object {
        $_.RuleId.ToUpperInvariant().Contains("TYPE-MISSING") -or ($_.Message.ToLowerInvariant().Contains("type") -and $_.Message.ToLowerInvariant().Contains("not found"))
    } | ForEach-Object { "{0} ``{1}`` {2}" -f $_.Location, $_.RuleId, $_.Message })
    if ($missingPackageFindings.Count -gt 0 -or $customDependencies.Count -gt 0) {
        $risks += New-Risk -Severity $(if ($missingPackageFindings.Count -gt 0) { "Blocker" } else { "High" }) `
            -Location "project.json dependencies" `
            -Component (Format-Examples $customDependencies) `
            -Evidence (Format-Examples ($missingPackageFindings + $typeMissingFindings)) `
            -FailureMode "Dependency restore or type resolution can fail; converted workflows may contain unresolved activities." `
            -Replacement "Migrate and publish Windows-compatible libraries first, or replace unavailable custom activities with supported UI Automation, API, or coded workflow implementations." `
            -Resolution "Identify the owning library/feed, confirm NuGet or Orchestrator credentials, obtain source/package access, check whether the package has a Windows-compatible build, republish or replace it, update feeds if needed, then rerun normal analysis and the ignore-missing-dependencies pass." `
            -Owner "Client Owner + Human + Coding Agent" `
            -Automation "Partial: the coding agent can map namespaces to packages, update project references, and rerun validation after access is available; humans must provide package ownership, feed credentials, source access, and runtime validation." `
            -Validation "Restore succeeds; SARIF has no missing package/type findings; migrated project opens and validates in Studio."
    }

    $expressionExamples = @(Get-XamlMatches $Project @('=\s*[''"]\[\s*\{\s*\}\s*\][''"]', '>\s*\[\s*\{\s*\}\s*\]\s*<'))
    $expressionExamples += @($Findings | Where-Object { $_.Message -match "BC36914|BC36915|\{\}" } | ForEach-Object { "{0} ``{1}`` {2}" -f $_.Location, $_.RuleId, $_.Message })
    if ($expressionExamples.Count -gt 0) {
        $risks += New-Risk -Severity "Blocker" -Location (Format-Examples $expressionExamples) -Component "Ambiguous VB array initializer {}" -Evidence (Format-Examples $expressionExamples) -FailureMode "Windows validation can fail because stricter type inference cannot infer the array element type." -Replacement "Use a typed initializer such as New Object() {} or explicit typed values matching the target property." -Resolution "Replace [{}] with a typed initializer such as [New Object() {}] only when the target property accepts an object array; otherwise inspect the activity property and provide explicit typed values that match the expected row or argument shape." -Owner "Coding Agent" -Automation "High: the coding agent can locate and update deterministic expression patterns, then verify property type/schema and rerun validation." -Validation "No BC36914/BC36915 or ST-PMG-002 equivalent findings; Windows validation/build passes."
    }

    $saveImageExamples = @(Get-ActivityExamples $Project @("SaveImage"))
    $saveImageExamples += @($Findings | Where-Object { $_.Message -match "SaveImage|MigrationNotImplemented" } | ForEach-Object { "{0} ``{1}`` {2}" -f $_.Location, $_.RuleId, $_.Message })
    if ($saveImageExamples.Count -gt 0) {
        $risks += New-Risk -Severity "Blocker" -Location (Format-Examples $saveImageExamples) -Component "Classic SaveImage activity" -Evidence (Format-Examples $saveImageExamples) -FailureMode "Workflow Migrator may not implement this conversion, leaving screenshot persistence unresolved." -Replacement "Windows-compatible screenshot/file persistence helper or supported image/file activities." -Resolution "Replace the unsupported save step with a Windows-compatible helper that writes the captured image to the expected file path, preserve downstream upload/use activities, and validate file creation in the target robot session." -Owner "Coding Agent + Human" -Automation "Partial: agent can add or refactor deterministic file/image save logic; human must validate screenshot capture, permissions, and downstream upload/use behavior in the target robot session." -Validation "No migration-not-implemented finding; screenshot file is created and consumed successfully at runtime."
    }

    $classicUia = @(Get-ActivityExamples $Project @("AttachBrowser", "AttachWindow", "Check", "Click", "ClickText", "ElementExists", "FindElement", "GetAttribute", "GetFullText", "GetText", "GetValue", "GetVisibleText", "Highlight", "Hover", "OpenBrowser", "SelectItem", "SetText", "TakeScreenshot", "TypeInto", "UiElementExists"))
    if ($classicUia.Count -gt 0 -or ($dependencies | Where-Object { $_.Name -eq "UiPath.UIAutomation.Activities" })) {
        $risks += New-Risk -Severity "High" -Location $(if ($classicUia.Count -gt 0) { Format-Examples $classicUia } else { "UiPath.UIAutomation.Activities dependency" }) -Component "Classic UI Automation activities" -Evidence (Format-Examples $classicUia) -FailureMode "Supported activities may migrate, but selectors, application scopes, null input element behavior, and runtime timing can change." -Replacement "Use modern UI Automation activities under stable Use Application/Browser scopes and Object Repository targets where appropriate." -Resolution "Run Workflow Migrator with the UIA extension enabled, inspect each generated Use Application/Browser scope and annotations, recapture unstable selectors, replace fragile classic patterns where needed, and smoke-test representative application flows." -Owner "Workflow Migrator + Human + Coding Agent" -Automation "Partial: Workflow Migrator handles supported conversions; agent can inspect generated scopes and repair obvious selector/scope structure; humans must validate UI behavior against the real applications." -Validation "Post-migration annotations reviewed; selectors and application smoke tests pass."
    }

    $imageUia = @(Get-ActivityExamples $Project @("ClickImage", "ClickOCRText", "FindImage", "ImageExists", "WaitImageAppear", "WaitImageVanish"))
    if ($imageUia.Count -gt 0) {
        $risks += New-Risk -Severity "High" -Location (Format-Examples $imageUia) -Component "Image/OCR-based UI Automation" -Evidence (Format-Examples $imageUia) -FailureMode "Image and OCR actions are sensitive to resolution, themes, OCR engine scope, and generated modern application scopes." -Replacement "Prefer selector-based modern UIA activities; keep OCR/image only where no stable selector exists." -Resolution "Review each image/OCR activity, determine whether a stable selector or accessible attribute exists, replace with selector-based modern UIA where possible, and validate remaining image/OCR steps under the target resolution/theme/OCR engine." -Owner "Coding Agent + Human" -Automation "Partial: agent can identify and replace obvious cases; human must validate against the real application UI." -Validation "No unexpected image/OCR migration warnings; target UI flow passes at runtime."
    }

    $productivity = @(Get-XamlMatches $Project @("GSuite|Google|Office365|Microsoft365", "UseConnectionService|ConnectionId|ServiceAccount|KeyPath"))
    if ($productivity.Count -gt 0 -or ($dependencies | Where-Object { $_.Name -in @("UiPath.GSuite.Activities", "UiPath.MicrosoftOffice365.Activities") })) {
        $risks += New-Risk -Severity "High" -Location $(if ($productivity.Count -gt 0) { Format-Examples $productivity } else { "Productivity activity dependency" }) -Component "GSuite/Microsoft 365 productivity connections" -Evidence (Format-Examples $productivity) -FailureMode "Migrated productivity activities may require Orchestrator connection IDs; local service-account keys and legacy auth can fail in the target environment." -Replacement "Provision Orchestrator connections and pass Workflow Migrator a --config=<connection.json> mapping for required ConnectionId values." -Resolution "Inventory every GSuite/Microsoft 365 scope/activity, provision the required Integration Service or Orchestrator connection IDs, prepare the CLI connection config JSON, remove or secure local key-file references, and test read/write/upload/send operations." -Owner "Client Owner + Human + Coding Agent" -Automation "Partial: agent can generate config templates and update references; client/human must provision connections and validate permissions." -Validation "Migrated project uses expected ConnectionId values; read/write/upload/send operations pass with non-production data."
    }

    $smtp = @(Get-XamlMatches $Project @("SMTP|SendSMTP|Smtp", '\b(Server|Port|From)=[''"]'))
    if ($smtp.Count -gt 0 -or ($dependencies | Where-Object { $_.Name -eq "UiPath.Mail.Activities" })) {
        $risks += New-Risk -Severity "Medium" -Location $(if ($smtp.Count -gt 0) { Format-Examples $smtp } else { "UiPath.Mail.Activities dependency" }) -Component "SMTP/Mail activities and hardcoded mail settings" -Evidence (Format-Examples $smtp) -FailureMode "Notifications can fail if relay, sender, authentication, package behavior, or network access changes in Windows runtime." -Replacement "Use Microsoft 365 connection activities when appropriate, or externalize SMTP relay settings into assets/configuration." -Resolution "Decide whether the target runtime should use SMTP relay or Microsoft 365 connection activities, provision the approved relay/connection, move server/sender/port/recipient values to config or assets, and send success/failure test notifications." -Owner "Client Owner + Coding Agent" -Automation "Partial: agent can refactor hardcoded values; client/human must approve relay/M365 connection strategy." -Validation "Success and failure notification smoke tests pass from the target robot environment."
    }

    $hardcoded = @(Get-XamlMatches $Project @("[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", '[A-Za-z]:\\[^''"]+', 'https?://[^''">\s]+', '\b(Server|Host|UserEmail|KeyPath|FolderId|FileId)=[''"][^''"]+[''"]') 20)
    if ($hardcoded.Count -gt 0) {
        $risks += New-Risk -Severity "Medium" -Location (Format-Examples $hardcoded) -Component "Hardcoded configuration values" -Evidence (Format-Examples $hardcoded) -FailureMode "Environment-specific paths, URLs, email addresses, IDs, or key paths may break after migration or expose secrets/configuration in source." -Replacement "Use Orchestrator assets, Config.xlsx, environment-specific settings, or secure credential stores." -Resolution "Classify each hardcoded value as environment configuration, identifier, path, endpoint, or secret; externalize it to Config.xlsx, Orchestrator assets, or credential storage; mask/rotate sensitive values where needed; then run with target-environment values." -Owner "Coding Agent + Human" -Automation "Partial: agent can identify and externalize obvious constants; human/client must confirm correct target values." -Validation "No target-environment constants remain in source; migrated run uses approved assets/configuration."
    }

    $soap = @(Get-XamlMatches $Project @("SOAP|WebService|ServiceReference"))
    if ($soap.Count -gt 0) {
        $risks += New-Risk -Severity "High" -Location (Format-Examples $soap) -Component "SOAP/web service integration" -Evidence (Format-Examples $soap) -FailureMode "SOAP web services are not supported in Windows and cross-platform projects." -Replacement "Replace with HTTP/REST calls, supported libraries, or a coded workflow/client compatible with the target runtime." -Resolution "Inventory each SOAP/service-reference call, obtain the service contract and test endpoint, choose a supported REST/HTTP/client-library or coded workflow replacement, refactor the call, and run integration tests before production migration." -Owner "Client Owner + Coding Agent" -Automation "Partial: agent can refactor once API contract is known; client/human must provide service contract and test access." -Validation "Replacement service calls pass integration tests in the target environment."
    }

    for ($i = 0; $i -lt $risks.Count; $i++) {
        $risks[$i] | Add-Member -NotePropertyName Id -NotePropertyValue ("R-{0:D3}" -f ($i + 1)) -Force
    }
    return $risks
}

function Get-Readiness {
    param([int]$AnalyzeExitCode, [object[]]$Risks, [string]$SarifPath)
    if ($AnalyzeExitCode -ne 0 -or ($Risks | Where-Object { $_.Severity -eq "Blocker" })) {
        return "Blocked"
    }
    if (-not $SarifPath) {
        return "Blocked"
    }
    if ($Risks | Where-Object { $_.Severity -eq "High" }) {
        return "High Risk"
    }
    if ($Risks | Where-Object { $_.Severity -eq "Medium" }) {
        return "Ready With Warnings"
    }
    return "Ready"
}

function Get-ApprovalRecommendation {
    param([string]$Status)
    if ($Status -eq "Blocked") { return "Do not approve upgrade yet. Resolve blocking issues and rerun analysis." }
    if ($Status -eq "High Risk") { return "Approve only after reviewing the highlighted activities/packages and accepting validation risk." }
    if ($Status -eq "Ready With Warnings") { return "Approve only after reviewing warnings and planned validation." }
    return "Ready for approval, subject to normal post-upgrade validation."
}

function Write-AnalysisReport {
    param(
        [string]$Path,
        [string]$Project,
        [string]$PlannedOutput,
        [string]$CliPath,
        [int]$AnalyzeExitCode,
        [string]$SarifPath,
        [object]$Sarif,
        [Nullable[int]]$DeepAnalyzeExitCode,
        [string]$DeepSarifPath,
        [object]$DeepSarif,
        [string[]]$PassThroughArgs = @()
    )

    $findings = @(Get-SarifFindings $Sarif)
    $deepFindings = @(Get-SarifFindings $DeepSarif)
    $allFindings = @($findings + $deepFindings | Sort-Object Level, RuleId, Message, Location -Unique)
    $risks = @(Get-AssessmentRisks $Project $allFindings)
    $status = Get-Readiness $AnalyzeExitCode $risks $SarifPath
    $blocking = @($risks | Where-Object { $_.Severity -eq "Blocker" })
    $high = @($risks | Where-Object { $_.Severity -eq "High" })
    $medium = @($risks | Where-Object { $_.Severity -eq "Medium" })
    $dependencies = @(Get-ProjectDependencies $Project | ForEach-Object { "$($_.Name) $($_.Version)" })
    $automated = @($allFindings | Where-Object { $_.RuleId -match "MAIL|OFFICE365|UIAUTOMATION|PACKAGE-UPGRADE|PACKAGE-MIGRATION|FRAMEWORK-UPDATE" })

    $lines = [System.Collections.Generic.List[string]]::new()
    $lines.Add("# Windows - Legacy to Windows Migration Risk Report")
    $lines.Add("")
    $lines.Add("## Executive Summary")
    $lines.Add("")
    $lines.Add(("- **Project:** ``{0}``" -f (Get-ProjectName $Project)))
    $lines.Add(("- **Current compatibility:** ``{0}``" -f (Get-ProjectTargetFramework $Project)))
    $lines.Add("- **Target compatibility:** Windows")
    $lines.Add(("- **Target Studio version for validation:** ``{0}``" -f $(if ($TargetStudioVersion) { $TargetStudioVersion } else { "Not specified" })))
    $lines.Add("- **Overall migration status:** $status")
    $lines.Add("- **Primary blockers:** $($blocking.Count)")
    $lines.Add("- **High-risk items:** $($high.Count)")
    $lines.Add("- **Medium-risk items:** $($medium.Count)")
    $lines.Add("- **Automated changes detected:** $($automated.Count)")
    $lines.Add("")

    $lines.Add("## Pre-Flight Status")
    $lines.Add("")
    Add-MarkdownTable $lines @("Check", "Result", "Evidence") @(
        @("Project path exists", "Yes", $Project),
        @("Analysis-only workflow used", "Yes", "The helper ran analyze; upgrade remains blocked until explicit approval."),
        @("Original project write migration performed", "No", "No upgrade command is run during the analysis phase."),
        @("Planned output path recorded", "Yes", $PlannedOutput)
    )

    $lines.Add("")
    $lines.Add("## Validation Evidence")
    $lines.Add("")
    $deepResult = if ($null -ne $DeepAnalyzeExitCode) { if ($DeepAnalyzeExitCode -eq 0) { "Pass" } else { "Fail" } } else { "Not run" }
    $deepEvidence = if ($null -ne $DeepAnalyzeExitCode) { "analyze --ignore-missing-dependencies exit code $DeepAnalyzeExitCode; SARIF $DeepSarifPath" } else { "No restore blocker was detected, or the option was already provided by the caller." }
    Add-MarkdownTable $lines @("Check", "Result", "Evidence") @(
        @("Workflow Migrator analysis", $(if ($AnalyzeExitCode -eq 0) { "Pass" } else { "Fail" }), "analyze exit code $AnalyzeExitCode; SARIF $SarifPath"),
        @("Workflow Migrator analysis with missing dependencies ignored", $deepResult, $deepEvidence),
        @("Dependencies reviewed", $(if ($dependencies.Count -gt 0) { "Yes" } else { "No" }), $(if ($dependencies.Count -gt 0) { $dependencies -join ", " } else { "No project.json dependencies parsed." }))
    )

    $lines.Add("")
    $lines.Add("## Package Version Selection and Studio Compatibility")
    $lines.Add("")
    Add-MarkdownTable $lines @("Decision point", "Observed/selected value", "Guidance") (Get-PackageVersionRows $TargetStudioVersion $PassThroughArgs)

    $lines.Add("")
    $lines.Add("## Migration Risks and Limitations")
    $lines.Add("")
    $lines.Add("- Analyzer findings are combined with project and XAML inspection so the report calls out likely runtime risks, not only SARIF rule counts.")
    $lines.Add("- The assessment cannot prove runtime business equivalence; selectors, credentials, assets, queues, connection names, file paths, and external services still require validation.")
    $lines.Add("- Custom and third-party activity packages require owner review because Windows compatibility depends on package implementation and available feeds.")
    $lines.Add("- A clean analysis report does not replace opening/building the migrated project in Studio and running representative workflow tests.")

    $lines.Add("")
    $lines.Add("## Migration Risks")
    $lines.Add("")
    if ($risks.Count -gt 0) {
        Add-MarkdownTable $lines @("ID", "Severity", "Location", "Problematic component", "Evidence", "Failure mode", "Recommended replacement", "Resolution steps", "Owner", "Automation eligibility", "Validation") @(
            $risks | ForEach-Object { @($_.Id, $_.Severity, $_.Location, $_.Component, $_.Evidence, $_.FailureMode, $_.Replacement, $_.Resolution, $_.Owner, $_.Automation, $_.Validation) }
        )
    } else {
        $lines.Add("- No known migration risk patterns were found beyond normal validation requirements.")
    }

    $lines.Add("")
    $lines.Add("## Blockers")
    $lines.Add("")
    if ($blocking.Count -gt 0) {
        foreach ($risk in $blocking) {
            $lines.Add("### $($risk.Id) - $($risk.Component)")
            $lines.Add("")
            $lines.Add("- **Where:** $($risk.Location)")
            $lines.Add("- **Evidence:** $($risk.Evidence)")
            $lines.Add("- **Why it blocks migration:** $($risk.FailureMode)")
            $lines.Add("- **Replacement:** $($risk.Replacement)")
            $lines.Add("- **Fix steps:** $($risk.Resolution)")
            $lines.Add("- **Owner:** $($risk.Owner)")
            $lines.Add("- **Can be automated:** $($risk.Automation)")
            $lines.Add("- **Validation:** $($risk.Validation)")
            $lines.Add("")
        }
    } else {
        $lines.Add("- None found.")
    }

    Add-ActionGuidance $lines $risks

    $lines.Add("")
    $lines.Add("## Automated Changes Detected")
    $lines.Add("")
    if ($automated.Count -gt 0) {
        Add-MarkdownTable $lines @("Rule", "Location", "Detected change", "Validation required") @(
            $automated | ForEach-Object { @($_.RuleId, $_.Location, $_.Message, "Validate behavior after upgrade, especially authentication, selectors, and external service calls.") }
        )
    } else {
        $lines.Add("- None found.")
    }

    $lines.Add("")
    $lines.Add("## Resolution Order")
    $lines.Add("")
    Add-MarkdownTable $lines @("Order", "Action", "Risk IDs", "Owner", "Exit criteria") @(
        @("1", "Preserve backup/source-control checkpoint and work on a copy", "All", "Coding Agent", "Backup/copy recorded before upgrade"),
        @("2", "Resolve dependency/feed/library blockers", (Format-Examples @($risks | Where-Object { $_.Component.ToLowerInvariant().Contains("package") -or $_.Component.ToLowerInvariant().Contains("activity types") } | ForEach-Object { $_.Id })), "Client Owner + Human + Coding Agent", "Restore and type-resolution findings are clean"),
        @("3", "Fix deterministic compile or migration blockers before upgrade", (Format-Examples @($blocking | Where-Object { $_.Component.ToLowerInvariant().Contains("array") -or $_.Component.ToLowerInvariant().Contains("saveimage") } | ForEach-Object { $_.Id })), "Coding Agent", "No known expression or migration-not-implemented blocker remains"),
        @("4", "Prepare connection/configuration strategy", (Format-Examples @($risks | Where-Object { $_.Component.ToLowerInvariant().Contains("connection") -or $_.Component.ToLowerInvariant().Contains("smtp") -or $_.Component.ToLowerInvariant().Contains("hardcoded") } | ForEach-Object { $_.Id })), "Client Owner + Human + Coding Agent", "Connection IDs, relay decisions, and config/assets are documented"),
        @("5", "Run Workflow Migrator pilot on a copy after approval", "All", "Workflow Migrator", "SARIF reviewed and no blockers remain"),
        @("6", "Fix converted validation/build issues", "All", "Coding Agent", "Windows project validates/builds"),
        @("7", "Validate UI scopes, selectors, connections, and business outcomes", "All", "Human + Coding Agent", "Representative smoke/regression tests pass")
    )

    $lines.Add("")
    $lines.Add("## Final Recommendation")
    $lines.Add("")
    $lines.Add((Get-ApprovalRecommendation $status))

    $lines.Add("")
    $lines.Add("## Official Guidance Used")
    $lines.Add("")
    $lines.Add("- UiPath Windows - Legacy compatibility guidance recommends inventorying projects, libraries, and dependencies; migrating libraries first; piloting conversion; validating external systems; and addressing known expression compatibility issues such as {} to new Object() {}.")
    $lines.Add("- UiPath Windows - Legacy dependency guidance states that conversion keeps the same package version when it exists in configured package sources, otherwise selects the highest patch of the nearest available version; unresolved dependencies remain migration blockers.")
    $lines.Add("- UiPath latest STS guidance states that STS no longer supports creating or editing Windows-Legacy source projects; validate converted Windows projects in STS only after conversion through a compatible path.")
    $lines.Add("- UiPath Workflow Migrator guidance recommends running analyze before upgrade, reviewing SARIF from the .upgrade folder, using --config=<connection.json> for productivity activity ConnectionId values, and validating generated UI Automation application scopes.")

    $lines.Add("")
    $lines.Add("## Finding Counts")
    $lines.Add("")
    foreach ($level in @("error", "warning", "note", "none")) {
        $count = @($findings | Where-Object { $_.Level -eq $level }).Count
        $lines.Add("- primary ${level}: $count")
    }
    if ($null -ne $DeepAnalyzeExitCode) {
        foreach ($level in @("error", "warning", "note", "none")) {
            $count = @($deepFindings | Where-Object { $_.Level -eq $level }).Count
            $lines.Add("- ignore-missing-dependencies ${level}: $count")
        }
    }

    $lines.Add("")
    $lines.Add("## Analysis Context")
    $lines.Add("")
    $lines.Add("- Generated UTC: $((Get-Date).ToUniversalTime().ToString("o"))")
    $lines.Add(("- Project path: ``{0}``" -f $Project))
    $lines.Add(("- Planned output path: ``{0}``" -f $PlannedOutput))
    $lines.Add(("- Workflow Migrator CLI: ``{0}``" -f $CliPath))
    $lines.Add(("- Primary SARIF source: ``{0}``" -f $(if ($SarifPath) { $SarifPath } else { "not found" })))
    $lines.Add(("- Ignore-missing-dependencies SARIF source: ``{0}``" -f $(if ($DeepSarifPath) { $DeepSarifPath } else { "not run or not found" })))

    if ($IncludeRawAnalyzerOutput) {
        $lines.Add("")
        $lines.Add("## Raw Analyzer Output")
        $lines.Add("")
        if ($allFindings.Count -gt 0) {
            foreach ($finding in $allFindings) {
                $location = if ($finding.Location) { " ($($finding.Location))" } else { "" }
                $lines.Add(("- [{0}] ``{1}``{2}: {3}" -f $finding.Level, $finding.RuleId, $location, $finding.Message))
            }
        } else {
            $lines.Add("- No analyzer findings to list.")
        }
    }

    if ($IncludeMigrationGate) {
        $lines.Add("")
        $lines.Add("## Migration Gate")
        $lines.Add("")
        $lines.Add("Do not run upgrade until the user has reviewed this report and explicitly approved migration.")
        $lines.Add("After approval, rerun the helper with -ApproveMigration.")
    }

    $parent = Split-Path -Parent $Path
    if ($parent) {
        New-Item -ItemType Directory -Path $parent -Force | Out-Null
    }
    Set-Content -LiteralPath $Path -Value ($lines -join [Environment]::NewLine) -Encoding UTF8
    return $Path
}

function Build-AnalyzeArgs {
    param([string]$Project, [string[]]$PassThrough)
    $args = @("analyze", "--project-path", $Project)
    if (-not (Test-CliOption $PassThrough @("--output-format", "-f"))) {
        $args += @("--output-format", "sarif")
    }
    $args += $PassThrough
    if ($CliVerbose -and -not (Test-CliOption $PassThrough @("--verbose", "-v"))) {
        $args += "--verbose"
    }
    return $args
}

function Run-ConsentGatedWorkflow {
    param([string]$CliPath)
    if (-not $ProjectPath) {
        Write-Error "-ProjectPath is required with -ConsentGated."
        return 2
    }
    $project = (Resolve-Path -LiteralPath $ProjectPath).Path
    $plannedOutput = if ($OutputPath) { $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($OutputPath) } else { "${project}_Upgraded" }
    $report = if ($ReportPath) { $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($ReportPath) } else { Join-Path $project ".upgrade\migration-analysis-report.md" }
    $passThrough = @($CliArgs)
    if ($passThrough.Count -gt 0 -and $passThrough[0] -eq "--") {
        $passThrough = @($passThrough | Select-Object -Skip 1)
    }

    Push-Location -LiteralPath $project
    try {
        $analyzeArgs = Build-AnalyzeArgs $project $passThrough
        $analyzeExitCode = Invoke-UpgradeCli $CliPath $analyzeArgs "migration analysis"
        $sarifPath = Get-LatestSarif $project
        $sarif = Read-JsonFile $sarifPath
        $findings = @(Get-SarifFindings $sarif)

        $deepAnalyzeExitCode = $null
        $deepSarifPath = $null
        $deepSarif = $null
        if ((Test-RestoreBlocker $findings) -and -not (Test-CliOption $passThrough @("--ignore-missing-dependencies"))) {
            $deepArgs = @($analyzeArgs + "--ignore-missing-dependencies")
            $deepAnalyzeExitCode = Invoke-UpgradeCli $CliPath $deepArgs "migration analysis with missing dependencies ignored"
            $latestDeep = Get-LatestSarif $project
            if ($latestDeep -ne $sarifPath) {
                $deepSarifPath = $latestDeep
                $deepSarif = Read-JsonFile $deepSarifPath
            }
        }

        $writtenReport = Write-AnalysisReport $report $project $plannedOutput $CliPath $analyzeExitCode $sarifPath $sarif $deepAnalyzeExitCode $deepSarifPath $deepSarif $passThrough
        Write-Host "Analysis report: $writtenReport"

        if ($analyzeExitCode -ne 0) {
            Write-Warning "Analyze failed. Review the report before attempting migration."
            return $analyzeExitCode
        }

        if (-not $ApproveMigration) {
            Write-Warning "Migration paused for user consent. Review the report, then rerun with -ApproveMigration."
            return $StopForConsentExitCode
        }

        $upgradeArgs = @("upgrade", "--project-path", $project) + $passThrough
        if ($OutputPath) {
            $upgradeArgs += @("--output-path", $plannedOutput)
        }
        if ($CliVerbose -and -not (Test-CliOption $passThrough @("--verbose", "-v"))) {
            $upgradeArgs += "--verbose"
        }
        $upgradeExitCode = Invoke-UpgradeCli $CliPath $upgradeArgs "migration upgrade"

        if (-not $SkipRemediation -and (Test-Path -LiteralPath $plannedOutput)) {
            $postArgs = Build-AnalyzeArgs $plannedOutput $passThrough
            [void](Invoke-UpgradeCli $CliPath $postArgs "post-upgrade analysis")
        }
        return $upgradeExitCode
    } finally {
        Pop-Location
    }
}

if ($PollIntervalSeconds -lt 5) {
    Write-Error "-PollIntervalSeconds must be at least 5."
    exit 2
}

$resolvedCli = Resolve-Cli
if ($Locate) {
    if (-not $resolvedCli) {
        Write-Error "Could not locate UiPath.Upgrade.Cli. Place it under $(Get-DefaultToolRoot) or pass -Cli."
        exit 2
    }
    Write-Output $resolvedCli
    exit 0
}

if (-not $resolvedCli) {
    Write-Error "Could not locate UiPath.Upgrade.Cli. Place it under $(Get-DefaultToolRoot) or pass -Cli."
    exit 2
}

if ($ConsentGated) {
    exit (Run-ConsentGatedWorkflow $resolvedCli)
}

if ($CliArgs.Count -gt 0 -and $CliArgs[0] -eq "--") {
    $CliArgs = @($CliArgs | Select-Object -Skip 1)
}
exit (Invoke-UpgradeCli $resolvedCli $CliArgs)
