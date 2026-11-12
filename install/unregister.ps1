<#
.SYNOPSIS
  Removes the Ink Math OneNote add-in registration for the current user (both 32-bit and 64-bit views).
#>
param([string]$KeyPrefix = 'Software')
$ErrorActionPreference = 'Stop'

$Clsid = '{7E3C1B52-4A9D-4F0E-9C61-2B8D5A4F3E17}'
$ProgId = 'InkMath.Connect'

foreach ($view in [Microsoft.Win32.RegistryView]::Registry32, [Microsoft.Win32.RegistryView]::Registry64) {
    $root = [Microsoft.Win32.RegistryKey]::OpenBaseKey([Microsoft.Win32.RegistryHive]::CurrentUser, $view)
    try {
        foreach ($path in "$KeyPrefix\Classes\CLSID\$Clsid", "$KeyPrefix\Classes\AppID\$Clsid", "$KeyPrefix\Classes\$ProgId",
                          "$KeyPrefix\Microsoft\Office\OneNote\AddIns\$ProgId") {
            $root.DeleteSubKeyTree($path, $false)
        }
    } finally { $root.Close() }
}
# Type library repairs written by register.ps1 (marked InkMathRepair); anything else there is left alone.
$TypeLib = '{0EA692EE-BB50-4E3C-AEF0-356D91732725}'
$root = [Microsoft.Win32.RegistryKey]::OpenBaseKey([Microsoft.Win32.RegistryHive]::CurrentUser, [Microsoft.Win32.RegistryView]::Default)
try {
    $lib = $root.OpenSubKey("$KeyPrefix\Classes\TypeLib\$TypeLib")
    if ($lib) {
        $ours = @($lib.GetSubKeyNames() | Where-Object { $lib.OpenSubKey($_).GetValue('InkMathRepair') -eq 1 })
        $lib.Close()
        foreach ($ver in $ours) { $root.DeleteSubKeyTree("$KeyPrefix\Classes\TypeLib\$TypeLib\$ver", $false) }
        $left = $root.OpenSubKey("$KeyPrefix\Classes\TypeLib\$TypeLib")
        if ($left -and $left.SubKeyCount -eq 0 -and $left.ValueCount -eq 0) { $left.Close(); $root.DeleteSubKey("$KeyPrefix\Classes\TypeLib\$TypeLib", $false) }
        elseif ($left) { $left.Close() }
    }
} finally { $root.Close() }

Write-Output "Unregistered Ink Math ($ProgId)."
