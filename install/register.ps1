<#
.SYNOPSIS
  Registers the Ink Math OneNote add-in for the current user (no admin), for both 32-bit and 64-bit OneNote.
.EXAMPLE
  .\register.ps1 -DllPath ..\addin\InkMath.AddIn\bin\Release\net48\InkMath.AddIn.dll -PythonExe ..\solver\.venv\Scripts\python.exe -SolverDir ..\solver
#>
param(
    [Parameter(Mandatory = $true)][string]$DllPath,
    [string]$PythonExe,
    [string]$SolverDir,
    # Handwriting reader (M4): its venv's python.exe, the reader folder, and the model files folder.
    [string]$ReaderPythonExe,
    [string]$ReaderDir,
    [string]$ModelsDir,
    [string]$KeyPrefix = 'Software',
    # Where Office registered the OneNote type library (overridable for tests).
    [string]$TypeLibSourceHive = 'LocalMachine',
    [string]$TypeLibSourceKey = 'SOFTWARE\Classes\TypeLib'
)
$ErrorActionPreference = 'Stop'

$Clsid = '{7E3C1B52-4A9D-4F0E-9C61-2B8D5A4F3E17}'
$ProgId = 'InkMath.Connect'

$dll = (Resolve-Path -LiteralPath $DllPath).ProviderPath
$codeBase = ([Uri]$dll).AbsoluteUri

function Set-Values($root, [string]$path, [hashtable]$values) {
    $k = $root.CreateSubKey($path)
    try {
        foreach ($name in $values.Keys) {
            $v = $values[$name]
            if ($v -is [int]) { $k.SetValue($name, $v, [Microsoft.Win32.RegistryValueKind]::DWord) }
            else { $k.SetValue($name, [string]$v, [Microsoft.Win32.RegistryValueKind]::String) }
        }
    } finally { $k.Close() }
}

# COM class registration lives under Classes, which Windows keeps separately for 32- and 64-bit processes.
foreach ($view in [Microsoft.Win32.RegistryView]::Registry32, [Microsoft.Win32.RegistryView]::Registry64) {
    $root = [Microsoft.Win32.RegistryKey]::OpenBaseKey([Microsoft.Win32.RegistryHive]::CurrentUser, $view)
    try {
        $classes = "$KeyPrefix\Classes"
        Set-Values $root "$classes\CLSID\$Clsid" @{ '' = $ProgId; 'AppID' = $Clsid }
        Set-Values $root "$classes\CLSID\$Clsid\InprocServer32" @{
            '' = 'mscoree.dll'
            'ThreadingModel' = 'Both'
            'Class' = 'InkMath.AddIn.Connect'
            'Assembly' = 'InkMath.AddIn, Version=1.0.0.0, Culture=neutral, PublicKeyToken=null'
            'RuntimeVersion' = 'v4.0.30319'
            'CodeBase' = $codeBase
        }
        Set-Values $root "$classes\CLSID\$Clsid\ProgId" @{ '' = $ProgId }
        Set-Values $root "$classes\AppID\$Clsid" @{ 'DllSurrogate' = '' }   # OneNote loads add-ins out of process
        Set-Values $root "$classes\$ProgId\CLSID" @{ '' = $Clsid }
    } finally { $root.Close() }
}

# The add-in entry OneNote reads at startup.
$root = [Microsoft.Win32.RegistryKey]::OpenBaseKey([Microsoft.Win32.RegistryHive]::CurrentUser, [Microsoft.Win32.RegistryView]::Default)
try {
    Set-Values $root "$KeyPrefix\Microsoft\Office\OneNote\AddIns\$ProgId" @{
        'LoadBehavior' = 3
        'FriendlyName' = 'Ink Math'
        'Description' = 'Solve handwritten math'
    }
} finally { $root.Close() }

# Office sometimes leaves a OneNote type library version with no file (e.g. "1.0" holding only a PIA name).
# OneNote then fails every late-bound call with "Library not registered". Point each such version at the
# registered file, per user, and mark the entry so unregister.ps1 removes only what this script wrote.
$TypeLib = '{0EA692EE-BB50-4E3C-AEF0-356D91732725}'
$broken = @(); $file = $null; $platform = $null
foreach ($view in [Microsoft.Win32.RegistryView]::Registry32, [Microsoft.Win32.RegistryView]::Registry64) {
    $src = [Microsoft.Win32.RegistryKey]::OpenBaseKey([Microsoft.Win32.RegistryHive]$TypeLibSourceHive, $view)
    try {
        $lib = $src.OpenSubKey("$TypeLibSourceKey\$TypeLib")
        if (-not $lib) { continue }
        foreach ($ver in $lib.GetSubKeyNames()) {
            $found = $false
            foreach ($p in 'win32', 'win64') {
                $k = $lib.OpenSubKey("$ver\0\$p")
                if ($k -and $k.GetValue('')) { $found = $true; if (-not $file) { $file = $k.GetValue(''); $platform = $p } }
            }
            if (-not $found -and $broken -notcontains $ver) { $broken += $ver }
        }
    } finally { $src.Close() }
}
if ($file -and $broken.Count) {
    $root = [Microsoft.Win32.RegistryKey]::OpenBaseKey([Microsoft.Win32.RegistryHive]::CurrentUser, [Microsoft.Win32.RegistryView]::Default)
    try {
        foreach ($ver in $broken) {
            Set-Values $root "$KeyPrefix\Classes\TypeLib\$TypeLib\$ver" @{ 'InkMathRepair' = 1 }
            Set-Values $root "$KeyPrefix\Classes\TypeLib\$TypeLib\$ver\0\$platform" @{ '' = $file }
            Write-Output "Repaired OneNote type library version $ver -> $file"
        }
    } finally { $root.Close() }
}

if ($PythonExe) {
    $settings = [ordered]@{
        pythonExe = (Resolve-Path -LiteralPath $PythonExe -ErrorAction SilentlyContinue).ProviderPath
        solverDir = if ($SolverDir) { (Resolve-Path -LiteralPath $SolverDir -ErrorAction SilentlyContinue).ProviderPath } else { $null }
    }
    if (-not $settings.pythonExe) { $settings.pythonExe = $PythonExe }
    if ($SolverDir -and -not $settings.solverDir) { $settings.solverDir = $SolverDir }
    foreach ($pair in @(@('readerPythonExe', $ReaderPythonExe), @('readerDir', $ReaderDir), @('modelsDir', $ModelsDir))) {
        if ($pair[1]) {
            $full = (Resolve-Path -LiteralPath $pair[1] -ErrorAction SilentlyContinue).ProviderPath
            $settings[$pair[0]] = if ($full) { $full } else { $pair[1] }
        }
    }
    $json = $settings | ConvertTo-Json
    $out = Join-Path (Split-Path -Parent $dll) 'inkmath.settings.json'
    [IO.File]::WriteAllText($out, $json, (New-Object Text.UTF8Encoding $false))
    Write-Output "Settings: $out"
}
Write-Output "Registered Ink Math ($ProgId) for 32- and 64-bit OneNote: $dll"
