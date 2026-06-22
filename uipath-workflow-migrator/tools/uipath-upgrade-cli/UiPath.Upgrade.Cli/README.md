# UiPath Upgrade CLI

A command-line tool for analyzing and upgrading UiPath projects to newer versions.

## Commands

### Analyze Command
Analyzes a project for migration without making changes.

```bash
UiPath.Upgrade.exe  analyze --project-path "C:\path\to\project"
```

### Upgrade Command
Upgrades/migrates the project or parts of it.

```bash
UiPath.Upgrade.exe  upgrade --project-path "C:\path\to\project"
```

### Bulk Command
Analyzes or upgrades all projects in a repository/folder by scanning for project.json files.

```bash
# Analyze all projects in a repository
UiPath.Upgrade.exe  bulk --path "C:\path\to\repository" --command analyze

# Upgrade all projects in a repository
UiPath.Upgrade.exe  bulk --path "C:\path\to\repository" --command upgrade

# Analyze with verbose logging
UiPath.Upgrade.exe  bulk --path "C:\path\to\repository" --command analyze --verbose

# Upgrade with custom output directory
UiPath.Upgrade.exe  bulk --path "C:\path\to\repository" --command upgrade --output-path "C:\output\projects"
```

#### Bulk Command Options
- `--path` / `-p`: Path to the repository/folder to analyze or upgrade (required)
- `--command` / `-c`: Command to run: "analyze" or "upgrade" (required)
- `--verbose` / `-v`: Enable verbose logging (optional)

**Note:** The bulk command also supports orchestrator authentication options and extension management options documented below. Results are automatically saved as SARIF files in the repository path.

## Common Options

All commands support these common options:

- `--project-path` / `-p`: Path to the project to analyze or upgrade (required for analyze/upgrade commands)
- `--output-path` / `-o`: Output folder where the project will be copied (optional)
- `--ignore-missing-dependencies`: Ignore missing dependencies during upgrade. Missing dependencies will appear as warnings, but workflows using those dependencies will report missing types, fail to compile, or fail to perform other needed migrations (optional)
- `--verbose` / `-v`: Enable verbose logging (optional)
- `--extension-directory` / `-e`: Directory to search for extensions. For advanced use only (optional)
- `--output-format` / `-f`: Output format: console (default) or sarif (optional)

## Extension Management Options

Control which extensions are enabled during analysis/upgrade. By default, all discovered extensions are enabled.

- `--enabled-extensions`: Comma-separated list of extension names to enable. Only the specified extensions will be enabled. Example: `--enabled-extensions OutlookMigration,CustomExtension`
- `--disabled-extensions`: Comma-separated list of extension names to disable. All extensions except the specified ones will be enabled. Example: `--disabled-extensions OutlookMigration`
- `--disable-all-extensions`: Disable all extensions. Useful for running analysis/upgrade without any extension-specific migrations

**Note:** These options are mutually exclusive - you can only use one at a time.

## Orchestrator Authentication Options

Configure Orchestrator connection for accessing library feeds and dependencies. If no orchestrator URL is specified, the connection information from Studio will be used.

- `--orchestrator-url`: The full orchestrator URL including organization name (e.g., `https://cloud.uipath.com/yourorg`). When specified, you must also provide credentials using either PAT or external application credentials
- `--orchestrator-tenant`: The orchestrator tenant name (defaults to 'DefaultTenant' if not specified)

### Authentication Methods

Choose one of the following authentication methods:

#### Personal Access Token (PAT)
- `--orchestrator-pat`: Personal Access Token for orchestrator authentication. Create a PAT with Orchestrator API access scope (OR.Execution.Read). See: https://docs.uipath.com/automation-suite/automation-suite/2.2510/admin-guide/external-applications-personal-access-tokens

#### External Application Credentials
- `--orchestrator-application-id`: OAuth application ID for orchestrator authentication. Used with `--orchestrator-application-secret`. To obtain this, configure an external application in Orchestrator: 1) Go to External Applications, 2) Add Application, 3) Select 'Confidential application', 4) Add scope with 'Application scope' and select 'OR.Execution.Read' permission. See: https://docs.uipath.com/orchestrator/standalone/2025.10/user-guide/managing-external-applications
- `--orchestrator-application-secret`: OAuth application secret for orchestrator authentication. Used with `--orchestrator-application-id`. This is generated when you create a confidential external application in Orchestrator

## Extension-Specific Options

Extensions may provide additional command-line options. These are dynamically loaded based on discovered extensions.

### Example: Outlook Activities Extension
- `--outlook-migration-enabled`: Enable Outlook activities migration during analysis/upgrade (default: true)
- `--outlook-package-version`: The version of the Microsoft Office 365 activities package to use for migration (default: "3.1.21")

Use `--help` with any command to see all available options including extension-specific options.

## Output Formats

### Console Output (default)
Displays a summary of the analysis/upgrade results in the console and generates HTML reports.

### SARIF Output
Outputs results in SARIF (Static Analysis Results Interchange Format) JSON format to stdout.

```bash
UiPath.Upgrade.exe  analyze --project-path "C:\path\to\project" --output-format sarif
```

## Examples

### Basic Analysis
```bash
UiPath.Upgrade.exe analyze --project-path "C:\MyUiPathProject"
```

### Verbose Upgrade
```bash
UiPath.Upgrade.exe upgrade --project-path "C:\MyUiPathProject" --verbose
```

### Upgrade with Custom Output Path
```bash
UiPath.Upgrade.exe upgrade --project-path "C:\MyUiPathProject" --output-path "C:\UpgradedProject"
```

### Upgrade Ignoring Missing Dependencies
```bash
UiPath.Upgrade.exe upgrade --project-path "C:\MyUiPathProject" --ignore-missing-dependencies
```

### Repository Analysis
```bash
UiPath.Upgrade.exe bulk --path "C:\MyUiPathProjects" --command analyze --verbose
```

### Repository Upgrade
```bash
UiPath.Upgrade.exe bulk --path "C:\MyUiPathProjects" --command upgrade
```

### Analysis with Specific Extensions Enabled
```bash
UiPath.Upgrade.exe analyze --project-path "C:\MyUiPathProject" --enabled-extensions OutlookMigration
```

### Upgrade with All Extensions Disabled
```bash
UiPath.Upgrade.exe upgrade --project-path "C:\MyUiPathProject" --disable-all-extensions
```

### Analysis with Orchestrator Authentication (PAT)
```bash
UiPath.Upgrade.exe analyze --project-path "C:\MyUiPathProject" --orchestrator-url "https://cloud.uipath.com/yourorg" --orchestrator-pat "your-personal-access-token"
```

### Analysis with Orchestrator Authentication (External Application)
```bash
UiPath.Upgrade.exe analyze --project-path "C:\MyUiPathProject" --orchestrator-url "https://cloud.uipath.com/yourorg" --orchestrator-application-id "your-app-id" --orchestrator-application-secret "your-app-secret"
```

### Analysis with Extension-Specific Options
```bash
UiPath.Upgrade.exe analyze --project-path "C:\MyUiPathProject" --outlook-migration-enabled false --outlook-package-version "3.2.0"
```

### SARIF Output for CI/CD Integration
```bash
UiPath.Upgrade.exe analyze --project-path "C:\MyUiPathProject" --output-format sarif > analysis-results.sarif
``` 