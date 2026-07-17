[CmdletBinding(SupportsShouldProcess)]
param(
    [Parameter(Mandatory = $true)]
    [string]$UnrealProjectDirectory,
    [switch]$Force
)

$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path -LiteralPath $UnrealProjectDirectory).Path
$uprojects = @(Get-ChildItem -LiteralPath $projectRoot -Filter '*.uproject' -File)
if ($uprojects.Count -ne 1) {
    throw "Expected exactly one .uproject in $projectRoot; found $($uprojects.Count)."
}

$source = Join-Path $PSScriptRoot '..\assets\unreal\Plugins\SpriteFluxUnrealGodotBridge'
$source = (Resolve-Path -LiteralPath $source).Path
$pluginsRoot = Join-Path $projectRoot 'Plugins'
$destination = Join-Path $pluginsRoot 'SpriteFluxUnrealGodotBridge'

if (Test-Path -LiteralPath $destination) {
    if (-not $Force) {
        throw "Plugin already exists at $destination. Re-run with -Force only after reviewing local changes."
    }
    $backup = "$destination.backup-$(Get-Date -Format 'yyyyMMdd-HHmmss')"
    if ($PSCmdlet.ShouldProcess($destination, "Move existing plugin to $backup")) {
        Move-Item -LiteralPath $destination -Destination $backup
    }
}

New-Item -ItemType Directory -Path $pluginsRoot -Force | Out-Null
if ($PSCmdlet.ShouldProcess($destination, 'Install SpriteFlux Unreal Godot Bridge')) {
    Copy-Item -LiteralPath $source -Destination $destination -Recurse
}

[pscustomobject]@{
    status = 'installed'
    project = $uprojects[0].FullName
    plugin = $destination
    version = '1.0.0'
}
