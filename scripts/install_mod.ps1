# Links mod\tf3_mcp_bridge into Transport Fever 3's local mods folder (Steam),
# using a directory junction so edits in this repo apply without copying.
# Usage: powershell -ExecutionPolicy Bypass -File scripts\install_mod.ps1 [-Copy] [-Uninstall]
param(
    [switch]$Copy,
    [switch]$Uninstall
)

$ErrorActionPreference = 'Stop'
$source = Join-Path $PSScriptRoot '..\mod\tf3_mcp_bridge' | Resolve-Path
$steam = (Get-ItemProperty HKCU:\Software\Valve\Steam).SteamPath
if (-not $steam) { throw 'Steam install not found in registry.' }

$targets = Get-ChildItem (Join-Path $steam 'userdata') -Directory |
    ForEach-Object { Join-Path $_.FullName '3493540\local\mods' } |
    Where-Object { Test-Path $_ }
if (-not $targets) { throw 'No Transport Fever 3 userdata found. Start the game once first.' }

foreach ($mods in $targets) {
    $dest = Join-Path $mods 'tf3_mcp_bridge'
    if (Test-Path $dest) {
        $item = Get-Item $dest -Force
        if ($item.LinkType) {
            # remove only the junction, never the repo files it points to
            $item.Delete()
        } else {
            Remove-Item $dest -Recurse -Force
        }
        Write-Host "Removed $dest"
    }
    if ($Uninstall) { continue }
    if ($Copy) {
        Copy-Item $source $dest -Recurse
        Write-Host "Copied mod to $dest"
    } else {
        New-Item -ItemType Junction -Path $dest -Target $source | Out-Null
        Write-Host "Linked $dest -> $source"
    }
}
