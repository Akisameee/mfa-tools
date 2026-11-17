#Requires -Version 5.1
<#
.SYNOPSIS
Clears Message From Aliens progress across all local slots, preserving settings.
.DESCRIPTION
Requires the game to be closed. Moves alienmessage*.sav* files to the Windows
Recycle Bin, including Steam-account subfolders and migration backups. Does not
launch the game, change Steam Cloud, or create another backup directory.
.EXAMPLE
.\scripts\reset-save.ps1 -WhatIf
.EXAMPLE
.\scripts\reset-save.ps1
#>
[CmdletBinding(SupportsShouldProcess = $true, ConfirmImpact = 'Medium')]
param(
    [string]$SaveDirectory = (Join-Path ([Environment]::GetFolderPath('UserProfile')) 'AppData\LocalLow\Artless Games\MessageFromAliens')
)

$ErrorActionPreference = 'Stop'

function Assert-GameClosed {
    if (Get-Process -Name 'MessageFromAliens' -ErrorAction SilentlyContinue) {
        throw 'MessageFromAliens.exe is running. Close the game before resetting progress.'
    }
}

Assert-GameClosed
$saveRoot = [IO.Path]::GetFullPath($SaveDirectory).TrimEnd('\', '/')
if ((Split-Path -Leaf $saveRoot) -ne 'MessageFromAliens' -or
    (Split-Path -Leaf (Split-Path -Parent $saveRoot)) -ne 'Artless Games') {
    throw 'SaveDirectory must be the MessageFromAliens folder inside Artless Games.'
}
if (-not (Test-Path -LiteralPath $saveRoot)) {
    Write-Output 'No game data directory found. Nothing to reset.'
    return
}
if (-not (Test-Path -LiteralPath $saveRoot -PathType Container)) {
    throw 'SaveDirectory is not a directory.'
}

# Resolve and inspect ancestors as well: a junction must not redirect deletion.
$ancestor = Get-Item -LiteralPath $saveRoot -Force
while ($null -ne $ancestor) {
    if ($ancestor.Attributes -band [IO.FileAttributes]::ReparsePoint) {
        throw "Refusing a linked save path: $($ancestor.FullName)"
    }
    $ancestor = $ancestor.Parent
}
$saveRoot = (Resolve-Path -LiteralPath $saveRoot).ProviderPath.TrimEnd('\')
$pending = New-Object 'System.Collections.Generic.Stack[string]'
$pending.Push($saveRoot)
$progress = New-Object 'System.Collections.Generic.List[string]'
while ($pending.Count -gt 0) {
    $directory = $pending.Pop()
    foreach ($item in Get-ChildItem -LiteralPath $directory -Force) {
        $resolved = [IO.Path]::GetFullPath($item.FullName)
        if (-not $resolved.StartsWith($saveRoot + '\', [StringComparison]::OrdinalIgnoreCase)) {
            throw "Path outside the game data directory: $resolved"
        }
        if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) {
            throw "Refusing a linked item: $resolved"
        }
        if ($item.PSIsContainer) {
            $pending.Push($resolved)
        } elseif ($item.Name -like 'alienmessage*.sav*') {
            $progress.Add($resolved)
        }
    }
}

if ($progress.Count -eq 0) {
    Write-Output 'No progress files found. Settings are unchanged.'
    return
}
Write-Output "Game data directory: $saveRoot"
Write-Output 'Disable Steam Cloud for this game before the next launch to prevent old progress from returning.'
$removed = 0
foreach ($file in $progress) {
    if ($PSCmdlet.ShouldProcess($file, 'Move progress file to the Windows Recycle Bin')) {
        Assert-GameClosed
        $current = Get-Item -LiteralPath $file -Force
        if ($current.PSIsContainer -or ($current.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
            throw "Progress file changed during reset: $file"
        }
        Add-Type -AssemblyName Microsoft.VisualBasic
        [Microsoft.VisualBasic.FileIO.FileSystem]::DeleteFile(
            $file,
            [Microsoft.VisualBasic.FileIO.UIOption]::OnlyErrorDialogs,
            [Microsoft.VisualBasic.FileIO.RecycleOption]::SendToRecycleBin,
            [Microsoft.VisualBasic.FileIO.UICancelOption]::ThrowException
        )
        $removed++
    }
}
if ($WhatIfPreference) {
    Write-Output "Preview complete: $($progress.Count) progress file(s) selected. No files changed."
} else {
    Write-Output "Reset complete: $removed progress file(s) moved to the Recycle Bin. Settings preserved; game left closed."
}
