<#
.SYNOPSIS
    Sets ACE's developer environment for the current Windows user (S00, ACE_MASTER_PLAN.md section 17.4).

.DESCRIPTION
    Points tool caches and toolchains at one drive and adds the tool folders to the user PATH.
    Run it ONCE in a normal PowerShell window - not from inside the Claude desktop app, whose sandbox
    redirects user-level registry writes. Safe to run again: it only adds what is missing.

.PARAMETER Drive
    Drive letter for caches and toolchains. Default: E.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File .\tools\dev\set-dev-env.ps1
#>
[CmdletBinding()]
param(
    [ValidatePattern('^[A-Za-z]$')]
    [string]$Drive = 'E'
)

$ErrorActionPreference = 'Stop'
$root = "${Drive}:"

# 1) Tool folders on the user PATH (kept as REG_EXPAND_SZ so %VARIABLES% inside it keep working).
$key = [Microsoft.Win32.Registry]::CurrentUser.OpenSubKey('Environment', $true)
try {
    $raw = [string]$key.GetValue('Path', '', [Microsoft.Win32.RegistryValueOptions]::DoNotExpandEnvironmentNames)
    $parts = [System.Collections.Generic.List[string]]::new()
    foreach ($p in ($raw -split ';')) { if ($p) { $parts.Add($p) } }
    foreach ($add in @("$root\.toolchains\cargo\bin", "$root\.toolchains\npm-global", "$root\.toolchains\uv-tools\bin")) {
        if (-not ($parts -contains $add)) { $parts.Add($add); Write-Host "PATH += $add" }
    }
    $key.SetValue('Path', ($parts -join ';'), [Microsoft.Win32.RegistryValueKind]::ExpandString)
}
finally {
    $key.Close()
}

# 2) User environment variables (each call also notifies Windows that the environment changed).
$vars = [ordered]@{
    RUSTUP_HOME           = "$root\.toolchains\rustup"
    CARGO_HOME            = "$root\.toolchains\cargo"
    UV_CACHE_DIR          = "$root\.cache\uv"
    UV_PYTHON_INSTALL_DIR = "$root\.toolchains\uv-python"
    UV_TOOL_DIR           = "$root\.toolchains\uv-tools"
    UV_TOOL_BIN_DIR       = "$root\.toolchains\uv-tools\bin"
    PIP_CACHE_DIR         = "$root\.cache\pip"
    PRE_COMMIT_HOME       = "$root\.cache\pre-commit"
    HF_HOME               = "$root\.cache\huggingface"
    ACE_MODELS_DIR        = "$root\ACE-Models"
}
foreach ($name in $vars.Keys) {
    New-Item -ItemType Directory -Force -Path $vars[$name] | Out-Null
    [Environment]::SetEnvironmentVariable($name, $vars[$name], 'User')
    Write-Host ('{0,-22} = {1}' -f $name, $vars[$name])
}

# 3) npm cache and pnpm store on the same drive.
& npm config set cache "$root\.cache\npm"
$pnpm = "$root\.toolchains\npm-global\pnpm.cmd"
if (Test-Path -LiteralPath $pnpm) { & $pnpm config set store-dir "$root\.cache\pnpm-store" --global }

Write-Host ''
Write-Host 'Done. Open a NEW terminal (and restart VS Code) so the changes take effect.'
