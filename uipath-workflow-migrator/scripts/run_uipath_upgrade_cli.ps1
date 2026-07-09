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
        & $fileName @argumentList
        return $LASTEXITCODE
    }

    $process = Start-Process -FilePath $fileName -ArgumentList $argumentList -NoNewWindow -PassThru
    $started = Get-Date
    while (-not $process.HasExited) {
        Start-Sleep -Seconds $PollIntervalSeconds
        $process.Refresh()
        if (-not $process.HasExited) {
            $elapsed = [int]((Get-Date) - $started).TotalSeconds
            Write-Error "$OperationName still running after ${elapsed}s; next status check in ${PollIntervalSeconds}s." -ErrorAction Continue
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
        [object[][]]$Rows
    )
    $Lines.Add("| " + ($Headers -join " | ") + " |")
    $Lines.Add("| " + (($Headers | ForEach-Object { "---" }) -join " | ") + " |")
    foreach ($row in $Rows) {
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
    $matches = @()
    foreach ($file in Get-XamlFiles $Project) {
        $lines = Get-Content -LiteralPath $file.FullName -Encoding UTF8 -ErrorAction SilentlyContinue
        for ($index = 0; $index -lt $lines.Count; $index++) {
            foreach ($pattern in $Patterns) {
                if ($lines[$index] -match $pattern) {
                    $snippet = (($lines[$index] -replace "\s+", " ").Trim())
                    $matches += "$(Get-RelativeLocation $Project $file.FullName ($index + 1)) $snippet"
                    if ($matches.Count -ge $Limit) {
                        return $matches
                    }
                    break
                }
            }
        }
    }
    return $matches
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
            -Resolution "Confirm feeds and credentials, obtain source or package access, inspect target frameworks, republish Windows-compatible libraries, then rerun analysis." `
            -Owner "Client Owner + Human + Coding Agent" `
            -Automation "Partial: the coding agent can update references after feeds/source are available; humans must provide package ownership and runtime validation." `
            -Validation "Restore succeeds; SARIF has no missing package/type findings; migrated project opens and validates in Studio."
    }

    $expressionExamples = @(Get-XamlMatches $Project @('=\s*[''"]\[\s*\{\s*\}\s*\][''"]', '>\s*\[\s*\{\s*\}\s*\]\s*<'))
    $expressionExamples += @($Findings | Where-Object { $_.Message -match "BC36914|BC36915|\{\}" } | ForEach-Object { "{0} ``{1}`` {2}" -f $_.Location, $_.RuleId, $_.Message })
    if ($expressionExamples.Count -gt 0) {
        $risks += New-Risk -Severity "Blocker" -Location (Format-Examples $expressionExamples) -Component "Ambiguous VB array initializer {}" -Evidence (Format-Examples $expressionExamples) -FailureMode "Windows validation can fail because stricter type inference cannot infer the array element type." -Replacement "Use a typed initializer such as New Object() {} or explicit typed values matching the target property." -Resolution "Replace ambiguous initializers, then verify the receiving activity property and workflow validation." -Owner "Coding Agent" -Automation "High: the coding agent can apply deterministic expression fixes, with schema/property verification." -Validation "No BC36914/BC36915 or ST-PMG-002 equivalent findings; Windows validation/build passes."
    }

    $saveImageExamples = @(Get-ActivityExamples $Project @("SaveImage"))
    $saveImageExamples += @($Findings | Where-Object { $_.Message -match "SaveImage|MigrationNotImplemented" } | ForEach-Object { "{0} ``{1}`` {2}" -f $_.Location, $_.RuleId, $_.Message })
    if ($saveImageExamples.Count -gt 0) {
        $risks += New-Risk -Severity "Blocker" -Location (Format-Examples $saveImageExamples) -Component "Classic SaveImage activity" -Evidence (Format-Examples $saveImageExamples) -FailureMode "Workflow Migrator may not implement this conversion, leaving screenshot persistence unresolved." -Replacement "Windows-compatible screenshot/file persistence helper or supported image/file activities." -Resolution "Refactor the screenshot save step before upgrade or immediately after migration, preserving downstream upload/use behavior." -Owner "Coding Agent + Human" -Automation "Partial: agent can refactor deterministic file save logic; human must validate screenshot capture in the target robot session." -Validation "No migration-not-implemented finding; screenshot file is created and consumed successfully at runtime."
    }

    $classicUia = @(Get-ActivityExamples $Project @("AttachBrowser", "AttachWindow", "Check", "Click", "ClickText", "ElementExists", "FindElement", "GetAttribute", "GetFullText", "GetText", "GetValue", "GetVisibleText", "Highlight", "Hover", "OpenBrowser", "SelectItem", "SetText", "TakeScreenshot", "TypeInto", "UiElementExists"))
    if ($classicUia.Count -gt 0 -or ($dependencies | Where-Object { $_.Name -eq "UiPath.UIAutomation.Activities" })) {
        $risks += New-Risk -Severity "High" -Location $(if ($classicUia.Count -gt 0) { Format-Examples $classicUia } else { "UiPath.UIAutomation.Activities dependency" }) -Component "Classic UI Automation activities" -Evidence (Format-Examples $classicUia) -FailureMode "Supported activities may migrate, but selectors, application scopes, null input element behavior, and runtime timing can change." -Replacement "Use modern UI Automation activities under stable Use Application/Browser scopes and Object Repository targets where appropriate." -Resolution "Run Workflow Migrator with UIA extension enabled, inspect generated scopes, recapture unstable selectors, and smoke-test representative application flows." -Owner "Workflow Migrator + Human + Coding Agent" -Automation "Partial: Workflow Migrator handles supported conversions; agent can organize obvious scopes; humans must validate UI behavior." -Validation "Post-migration annotations reviewed; selectors and application smoke tests pass."
    }

    $imageUia = @(Get-ActivityExamples $Project @("ClickImage", "ClickOCRText", "FindImage", "ImageExists", "WaitImageAppear", "WaitImageVanish"))
    if ($imageUia.Count -gt 0) {
        $risks += New-Risk -Severity "High" -Location (Format-Examples $imageUia) -Component "Image/OCR-based UI Automation" -Evidence (Format-Examples $imageUia) -FailureMode "Image and OCR actions are sensitive to resolution, themes, OCR engine scope, and generated modern application scopes." -Replacement "Prefer selector-based modern UIA activities; keep OCR/image only where no stable selector exists." -Resolution "Review each image/OCR activity, replace with selector-based actions when possible, and validate screen resolution/OCR behavior." -Owner "Coding Agent + Human" -Automation "Partial: agent can identify and replace obvious cases; human must validate against the real application UI." -Validation "No unexpected image/OCR migration warnings; target UI flow passes at runtime."
    }

    $productivity = @(Get-XamlMatches $Project @("GSuite|Google|Office365|Microsoft365", "UseConnectionService|ConnectionId|ServiceAccount|KeyPath"))
    if ($productivity.Count -gt 0 -or ($dependencies | Where-Object { $_.Name -in @("UiPath.GSuite.Activities", "UiPath.MicrosoftOffice365.Activities") })) {
        $risks += New-Risk -Severity "High" -Location $(if ($productivity.Count -gt 0) { Format-Examples $productivity } else { "Productivity activity dependency" }) -Component "GSuite/Microsoft 365 productivity connections" -Evidence (Format-Examples $productivity) -FailureMode "Migrated productivity activities may require Orchestrator connection IDs; local service-account keys and legacy auth can fail in the target environment." -Replacement "Provision Orchestrator connections and pass Workflow Migrator a --config=<connection.json> mapping for required ConnectionId values." -Resolution "Inventory every productivity scope/activity, create connection IDs, prepare config JSON, and remove or secure local key-file references." -Owner "Client Owner + Human + Coding Agent" -Automation "Partial: agent can generate config templates and update references; client/human must provision connections and validate permissions." -Validation "Migrated project uses expected ConnectionId values; read/write/upload/send operations pass with non-production data."
    }

    $smtp = @(Get-XamlMatches $Project @("SMTP|SendSMTP|Smtp", '\b(Server|Port|From)=[''"]'))
    if ($smtp.Count -gt 0 -or ($dependencies | Where-Object { $_.Name -eq "UiPath.Mail.Activities" })) {
        $risks += New-Risk -Severity "Medium" -Location $(if ($smtp.Count -gt 0) { Format-Examples $smtp } else { "UiPath.Mail.Activities dependency" }) -Component "SMTP/Mail activities and hardcoded mail settings" -Evidence (Format-Examples $smtp) -FailureMode "Notifications can fail if relay, sender, authentication, package behavior, or network access changes in Windows runtime." -Replacement "Use Microsoft 365 connection activities when appropriate, or externalize SMTP relay settings into assets/configuration." -Resolution "Decide SMTP versus M365, provision the connection or relay, move hardcoded server/sender/port values to config/assets, and send test notifications." -Owner "Client Owner + Coding Agent" -Automation "Partial: agent can refactor hardcoded values; client/human must approve relay/M365 connection strategy." -Validation "Success and failure notification smoke tests pass from the target robot environment."
    }

    $hardcoded = @(Get-XamlMatches $Project @("[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", '[A-Za-z]:\\[^''"]+', 'https?://[^''">\s]+', '\b(Server|Host|UserEmail|KeyPath|FolderId|FileId)=[''"][^''"]+[''"]') 20)
    if ($hardcoded.Count -gt 0) {
        $risks += New-Risk -Severity "Medium" -Location (Format-Examples $hardcoded) -Component "Hardcoded configuration values" -Evidence (Format-Examples $hardcoded) -FailureMode "Environment-specific paths, URLs, email addresses, IDs, or key paths may break after migration or expose secrets/configuration in source." -Replacement "Use Orchestrator assets, Config.xlsx, environment-specific settings, or secure credential stores." -Resolution "Classify each hardcoded value, externalize environment-specific settings, and mask or rotate sensitive values where needed." -Owner "Coding Agent + Human" -Automation "Partial: agent can identify and externalize obvious constants; human/client must confirm correct target values." -Validation "No target-environment constants remain in source; migrated run uses approved assets/configuration."
    }

    $soap = @(Get-XamlMatches $Project @("SOAP|WebService|ServiceReference"))
    if ($soap.Count -gt 0) {
        $risks += New-Risk -Severity "High" -Location (Format-Examples $soap) -Component "SOAP/web service integration" -Evidence (Format-Examples $soap) -FailureMode "SOAP web services are not supported in Windows and cross-platform projects." -Replacement "Replace with HTTP/REST calls, supported libraries, or a coded workflow/client compatible with the target runtime." -Resolution "Inventory service calls, confirm available replacement API/client, then refactor before or after pilot migration." -Owner "Client Owner + Coding Agent" -Automation "Partial: agent can refactor once API contract is known; client/human must provide service contract and test access." -Validation "Replacement service calls pass integration tests in the target environment."
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
        [object]$DeepSarif
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
    $lines.Add("## Final Recommendation")
    $lines.Add("")
    $lines.Add((Get-ApprovalRecommendation $status))

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

    $writtenReport = Write-AnalysisReport $report $project $plannedOutput $CliPath $analyzeExitCode $sarifPath $sarif $deepAnalyzeExitCode $deepSarifPath $deepSarif
    Write-Output "Analysis report: $writtenReport"

    if ($analyzeExitCode -ne 0) {
        Write-Error "Analyze failed. Review the report before attempting migration." -ErrorAction Continue
        return $analyzeExitCode
    }

    if (-not $ApproveMigration) {
        Write-Error "Migration paused for user consent. Review the report, then rerun with -ApproveMigration." -ErrorAction Continue
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
