param(
    [ValidateSet("codex", "cursor", "copilot", "gemini", "opencode", "autopilot", "agents", "all", "none")]
    [string]$Agent = "all",

    [ValidateSet("global", "local")]
    [string]$Scope = "global",

    [string[]]$Target = @(),

    [ValidateSet("copy", "symlink")]
    [string]$Mode = "copy",

    [switch]$Force,

    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

$SkillName = "uipath-workflow-migrator"
$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$Source = Join-Path $RepoRoot $SkillName

if (-not (Test-Path (Join-Path $Source "SKILL.md") -PathType Leaf)) {
    throw "Missing skill source at $Source"
}

function Get-HomePath {
    if ($HOME) {
        return $HOME
    }
    if ($env:USERPROFILE) {
        return $env:USERPROFILE
    }
    throw "Unable to determine the current user's home directory."
}

function Add-Target {
    param(
        [System.Collections.Generic.List[string]]$Targets,
        [string]$Path
    )

    if ([string]::IsNullOrWhiteSpace($Path)) {
        return
    }

    $expanded = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($Path)
    if (-not $Targets.Contains($expanded)) {
        $Targets.Add($expanded)
    }
}

function Get-AgentTargets {
    param(
        [string]$Agent,
        [string]$Scope,
        [string[]]$ExplicitTargets
    )

    $homeDir = Get-HomePath
    $targets = [System.Collections.Generic.List[string]]::new()

    if ($Agent -eq "codex" -or $Agent -eq "agents" -or $Agent -eq "all") {
        if ($Scope -eq "global") {
            Add-Target $targets (Join-Path $homeDir ".agents/skills")
        } else {
            Add-Target $targets ".agents/skills"
        }
    }

    if ($Agent -eq "cursor" -or $Agent -eq "all") {
        if ($Scope -eq "global") {
            Add-Target $targets (Join-Path $homeDir ".cursor/skills")
        } else {
            Add-Target $targets ".cursor/skills"
        }
    }

    if ($Agent -eq "copilot" -or $Agent -eq "all") {
        if ($Scope -eq "global") {
            Add-Target $targets (Join-Path $homeDir ".github/skills")
        } else {
            Add-Target $targets ".github/skills"
        }
    }

    if ($Agent -eq "gemini" -or $Agent -eq "all") {
        if ($Scope -eq "global") {
            Add-Target $targets (Join-Path $homeDir ".gemini/skills")
        } else {
            Add-Target $targets ".gemini/skills"
        }
    }

    if ($Agent -eq "opencode" -or $Agent -eq "all") {
        if ($Scope -eq "global") {
            Add-Target $targets (Join-Path $homeDir ".config/opencode/skills")
        } else {
            Add-Target $targets ".opencode/skills"
        }
    }

    if ($Agent -eq "autopilot" -or $Agent -eq "all") {
        if ($Scope -eq "global") {
            Add-Target $targets (Join-Path $homeDir ".autopilot/skills")
        } else {
            Add-Target $targets ".autopilot/skills"
        }
    }

    foreach ($item in $ExplicitTargets) {
        Add-Target $targets $item
    }

    return $targets
}

function Remove-Existing {
    param([string]$Path)

    if (-not (Test-Path -LiteralPath $Path)) {
        return
    }

    $item = Get-Item -LiteralPath $Path -Force
    $isReparsePoint = ($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0

    if ($isReparsePoint -or -not $item.PSIsContainer) {
        Remove-Item -LiteralPath $Path -Force
    } else {
        Remove-Item -LiteralPath $Path -Recurse -Force
    }
}

function Install-Skill {
    param(
        [string]$Source,
        [string]$Destination,
        [string]$Mode,
        [bool]$Force,
        [bool]$DryRun
    )

    if (Test-Path $Destination) {
        if (-not $Force) {
            throw "$Destination already exists; pass -Force to replace it."
        }
        if ($DryRun) {
            Write-Output "would replace $Destination"
        } else {
            Remove-Existing $Destination
        }
    }

    if ($DryRun) {
        if ($Mode -eq "copy") {
            Write-Output "would copy $Source -> $Destination"
        } else {
            Write-Output "would symlink $Destination -> $Source"
        }
        return
    }

    $parent = Split-Path -Parent $Destination
    New-Item -ItemType Directory -Path $parent -Force | Out-Null

    if ($Mode -eq "copy") {
        Copy-Item -Path $Source -Destination $Destination -Recurse
    } else {
        New-Item -ItemType SymbolicLink -Path $Destination -Target $Source | Out-Null
    }

    Write-Output "installed $SkillName at $Destination"
}

$targets = Get-AgentTargets -Agent $Agent -Scope $Scope -ExplicitTargets $Target
if ($targets.Count -eq 0) {
    throw "No targets selected; pass -Agent or -Target."
}

foreach ($targetDir in $targets) {
    $destination = Join-Path $targetDir $SkillName
    Install-Skill -Source $Source -Destination $destination -Mode $Mode -Force:$Force.IsPresent -DryRun:$DryRun.IsPresent
}
