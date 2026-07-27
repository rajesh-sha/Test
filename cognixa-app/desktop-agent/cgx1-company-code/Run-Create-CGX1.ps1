<#
.SYNOPSIS
  Cognixa Desktop Agent — create or verify company code CGX1 on A4H via SAP GUI Scripting.

.DESCRIPTION
  This is the REAL write path. Cognixa HTML only simulates; this script drives SAP GUI on your PC.
  Run via run.cmd after Extract All (do not run from inside the zip).

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
$logPath = Join-Path $here 'agent-run.log'

function Write-Status([string]$Message, [string]$Color = 'White') {
  $ts = Get-Date -Format 'HH:mm:ss'
  $line = "[$ts] $Message"
  Write-Host $line -ForegroundColor $Color
}

try {
  Write-Status "Cognixa Desktop Agent starting..." 'Cyan'
  Write-Status "Folder: $here"

  if ($here -match '(?i)\\AppData\\Local\\Temp\\|\\.zip($|\\)') {
    throw "Running from a temp/zip path. Extract All the zip to a normal folder (e.g. Desktop), then run run.cmd from the extracted folder."
  }

  if (-not (Test-Path $payloadPath)) { throw "Missing payload.json next to this script. Extract the full zip." }
  if (-not (Test-Path $vbsPath)) { throw "Missing Create-CGX1.vbs next to this script. Extract the full zip." }

  $cscript = Get-Command cscript.exe -ErrorAction SilentlyContinue
  if (-not $cscript) { throw "cscript.exe not found. Windows Script Host is required for SAP GUI Scripting VBS." }

  $payload = Get-Content -Raw -Path $payloadPath | ConvertFrom-Json
  $sys = $payload.system
  $cc = $payload.companyCode

  $conn = if ($env:CGX_SAP_CONNECTION) { $env:CGX_SAP_CONNECTION } else { $sys.connectionDescription }
  $client = if ($env:CGX_SAP_CLIENT) { $env:CGX_SAP_CLIENT } else { $sys.client }
  $user = if ($env:CGX_SAP_USER) { $env:CGX_SAP_USER } else { $sys.user }
  $lang = if ($env:CGX_SAP_LANGUAGE) { $env:CGX_SAP_LANGUAGE } else { $sys.language }
  $bukrs = if ($env:CGX_CC) { $env:CGX_CC } else { $cc.bukrs }

  Write-Status "Connection : $conn"
  Write-Status "Client/User: $client / $user / $lang"
  Write-Status "Mode       : $(if ($VerifyOnly) { 'VERIFY' } else { 'CREATE (real SAP write)' })"
  Write-Status "Truth      : Browser Cognixa cannot write T001 — this agent can."

  # Preflight: SAP GUI scripting engine reachable?
  $sapOk = $false
  try {
    $gui = [Runtime.InteropServices.Marshal]::GetActiveObject('SAPGUI')
    if ($gui) { $sapOk = $true }
  } catch {
    try {
      $gui = New-Object -ComObject Sapgui.ScriptingCtrl.1
      if ($gui) { $sapOk = $true }
    } catch {
      $sapOk = $false
    }
  }
  if (-not $sapOk) {
    Write-Status "SAP GUI Scripting COM not found yet. Will still try via VBS after you ensure SAP Logon is installed." 'Yellow'
    Write-Status "Enable: SAP GUI Options -> Scripting ON, and RZ11 sapgui/user_scripting=TRUE" 'Yellow'
  } else {
    Write-Status "SAP GUI Scripting COM is available." 'Green'
  }

  if (-not $Password) {
    if ($env:CGX_SAP_PASSWORD) {
      $Password = ConvertTo-SecureString $env:CGX_SAP_PASSWORD -AsPlainText -Force
      Write-Status "Using password from CGX_SAP_PASSWORD env (session only)." 'DarkYellow'
    } else {
      Write-Status "Waiting for SAP password prompt..." 'Cyan'
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
    throw "Password is required to log on to SAP GUI. Re-run run.cmd and enter the password when prompted."
  }

  $mode = if ($VerifyOnly) { 'verify' } else { 'create' }
  Write-Status "Launching Create-CGX1.vbs mode=$mode ..." 'Cyan'

  $argList = @(
    '//nologo',
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

  $psi = New-Object System.Diagnostics.ProcessStartInfo
  $psi.FileName = 'cscript.exe'
  $psi.Arguments = ($argList -join ' ')
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

  if ($stdout) { Write-Host $stdout.TrimEnd() }
  if ($stderr) { Write-Host $stderr.TrimEnd() -ForegroundColor DarkYellow }

  $code = $proc.ExitCode
  switch ($code) {
    0 { Write-Status "SUCCESS — check OX02 / SE16N T001 for $bukrs" 'Green' }
    1 { Write-Status "VERIFY — $bukrs not found (expected before first create)" 'Yellow' }
    7 { Write-Status "PARTIAL — confirm transport popup in SAP GUI, then re-run with -VerifyOnly" 'Yellow' }
    default { Write-Status "FAILED (exit $code). See README for scripting prerequisites / field-ID re-record." 'Red' }
  }

  Write-Status "Preferred bulk path remains BC Sets (SCPR20) + CTS. This agent is residual." 'DarkGray'
  exit $code
}
catch {
  Write-Status ("ERROR: " + $_.Exception.Message) 'Red'
  Write-Status "Fix: Extract All zip -> open extracted folder -> double-click run.cmd" 'Yellow'
  Write-Status "Also need SAP GUI for Windows + scripting enabled." 'Yellow'
  exit 10
}
