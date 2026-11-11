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
Write-Output "Unregistered Ink Math ($ProgId)."
