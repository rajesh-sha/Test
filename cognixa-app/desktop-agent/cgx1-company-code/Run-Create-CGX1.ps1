<#
.SYNOPSIS
  Cognixa Desktop Agent — create or verify company code CGX1 on A4H via SAP GUI Scripting.

.DESCRIPTION
  This is the REAL write path. Cognixa HTML only simulates; this script drives SAP GUI on your PC.

.PARAMETER VerifyOnly
  Only check whether the company code exists in OX02.

.PARAMETER Password
  Optional. If omitted, a secure prompt is shown. Never commit passwords.
#>
[CmdletBinding()]
param(
  [switch]$VerifyOnly,
  [SecureString]$Password
)

$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$payloadPath = Join-Path $here 'payload.json'
$vbsPath = Join-Path $here 'Create-CGX1.vbs'

if (-not (Test-Path $payloadPath)) { throw "Missing payload.json next to this script." }
if (-not (Test-Path $vbsPath)) { throw "Missing Create-CGX1.vbs next to this script." }

$payload = Get-Content -Raw -Path $payloadPath | ConvertFrom-Json
$sys = $payload.system
$cc = $payload.companyCode

$conn = if ($env:CGX_SAP_CONNECTION) { $env:CGX_SAP_CONNECTION } else { $sys.connectionDescription }
$client = if ($env:CGX_SAP_CLIENT) { $env:CGX_SAP_CLIENT } else { $sys.client }
$user = if ($env:CGX_SAP_USER) { $env:CGX_SAP_USER } else { $sys.user }
$lang = if ($env:CGX_SAP_LANGUAGE) { $env:CGX_SAP_LANGUAGE } else { $sys.language }
$bukrs = if ($env:CGX_CC) { $env:CGX_CC } else { $cc.bukrs }

Write-Host ""
Write-Host "Cognixa Desktop Agent — company code $bukrs" -ForegroundColor Cyan
Write-Host "Connection : $conn"
Write-Host "Client/User: $client / $user / $lang"
Write-Host "Mode       : $(if ($VerifyOnly) { 'VERIFY' } else { 'CREATE (real SAP write)' })"
Write-Host "Truth      : Browser Cognixa cannot write T001 — this agent can."
Write-Host ""

if (-not $Password) {
  if ($env:CGX_SAP_PASSWORD) {
    $Password = ConvertTo-SecureString $env:CGX_SAP_PASSWORD -AsPlainText -Force
    Write-Host "Using password from CGX_SAP_PASSWORD env (session only)." -ForegroundColor DarkYellow
  } else {
    $Password = Read-Host "SAP GUI password for $user (not saved)" -AsSecureString
  }
}

$bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($Password)
try {
  $plain = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)
} finally {
  [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr) | Out-Null
}

if ([string]::IsNullOrWhiteSpace($plain)) {
  throw "Password is required to log on to SAP GUI."
}

$mode = if ($VerifyOnly) { 'verify' } else { 'create' }
$args = @(
  "//nologo",
  "`"$vbsPath`"",
  "`"$conn`"",
  "`"$client`"",
  "`"$user`"",
  "`"$plain`"",
  "`"$lang`"",
  "`"$bukrs`"",
  "`"$($cc.butxt)`"",
  "`"$($cc.ort01)`"",
  "`"$($cc.land1)`"",
  "`"$($cc.waers)`"",
  "`"$($cc.spras)`"",
  "`"$mode`""
)

# Clear plain ASAP from PS variable after starting — still in process args briefly (Windows limitation)
$psi = New-Object System.Diagnostics.ProcessStartInfo
$psi.FileName = "cscript.exe"
$psi.Arguments = ($args -join ' ')
$psi.RedirectStandardOutput = $true
$psi.RedirectStandardError = $true
$psi.UseShellExecute = $false
$psi.CreateNoWindow = $true

$proc = New-Object System.Diagnostics.Process
$proc.StartInfo = $psi
[void]$proc.Start()
$stdout = $proc.StandardOutput.ReadToEnd()
$stderr = $proc.StandardError.ReadToEnd()
$proc.WaitForExit()
$plain = $null
[GC]::Collect()

Write-Host $stdout
if ($stderr) { Write-Host $stderr -ForegroundColor DarkYellow }

$code = $proc.ExitCode
switch ($code) {
  0 { Write-Host "SUCCESS — check OX02 / SE16N T001 for $bukrs" -ForegroundColor Green }
  1 { Write-Host "VERIFY — $bukrs not found (expected before first create)" -ForegroundColor Yellow }
  7 { Write-Host "PARTIAL — confirm transport popup in SAP GUI, then re-run -VerifyOnly" -ForegroundColor Yellow }
  default { Write-Host "FAILED (exit $code). See README for scripting prerequisites / field-ID re-record." -ForegroundColor Red }
}

Write-Host ""
Write-Host "Preferred bulk path remains BC Sets (SCPR20) + CTS. This agent is residual." -ForegroundColor DarkGray
exit $code
