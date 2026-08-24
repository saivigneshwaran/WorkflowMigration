param(
    [string]$RepoUrl = "https://github.com/saivigneshwaran/WorkflowMigration.git",
    [string]$Target = "WorkflowMigration",
    [string]$Branch = "main"
)

$ErrorActionPreference = "Stop"

$resolvedTarget = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($Target)
$upgradeCliPath = Join-Path $resolvedTarget "uipath-workflow-migrator\tools\uipath-upgrade-cli\UiPath.Upgrade.Cli"
$gitDir = Join-Path $resolvedTarget ".git"

if (Test-Path $upgradeCliPath) {
    if (-not (Test-Path $gitDir)) {
        throw "$resolvedTarget already contains the Upgrade CLI but is not a git checkout; remove it or choose a different -Target."
    }

    Write-Output "Upgrade CLI found at $upgradeCliPath; fetching only the update."
    Push-Location $resolvedTarget
    try {
        git fetch origin $Branch
        git pull --ff-only origin $Branch
    } finally {
        Pop-Location
    }
} elseif (Test-Path $resolvedTarget) {
    throw "$resolvedTarget already exists but does not contain the Upgrade CLI; remove it or choose a different -Target."
} else {
    Write-Output "Upgrade CLI not found; cloning repository into $resolvedTarget."
    git clone --branch $Branch $RepoUrl $resolvedTarget
}
