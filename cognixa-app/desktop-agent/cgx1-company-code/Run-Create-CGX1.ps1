# Cognixa Desktop Agent - create or verify company code CGX1 on A4H via SAP GUI Scripting.
# ASCII-only file (Windows PowerShell 5.x safe). Run via run.cmd after Extract All.
[CmdletBinding()]
param(
  [switch]$VerifyOnly,
  [SecureString]$Password
)

$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$payloadPath = Join-Path $here 'payload.json'
$vbsPath = Join-Path $here 'Create-CGX1.vbs'

function Write-Status {
  param(
    [Parameter(Mandatory = $true)][string]$Message,
    [string]$Color = 'White'
  )
  $ts = Get-Date -Format 'HH:mm:ss'
  Write-Host ("[{0}] {1}" -f $ts, $Message) -ForegroundColor $Color
}

try {
  Write-Status -Message 'Cognixa Desktop Agent starting...' -Color Cyan
  Write-Status -Message ("Folder: {0}" -f $here)

  if ($here -match '(?i)\\AppData\\Local\\Temp\\|\\.zip($|\\)') {
    throw 'Running from a temp/zip path. Extract All the zip to a normal folder (e.g. Desktop), then run run.cmd from the extracted folder.'
  }

  if (-not (Test-Path -LiteralPath $payloadPath)) {
    throw 'Missing payload.json next to this script. Extract the full zip.'
  }
  if (-not (Test-Path -LiteralPath $vbsPath)) {
    throw 'Missing Create-CGX1.vbs next to this script. Extract the full zip.'
  }

  $cscript = Get-Command cscript.exe -ErrorAction SilentlyContinue
  if (-not $cscript) {
    throw 'cscript.exe not found. Windows Script Host is required for SAP GUI Scripting VBS.'
  }

  $payload = Get-Content -LiteralPath $payloadPath -Raw -Encoding UTF8 | ConvertFrom-Json
  $sys = $payload.system
  $cc = $payload.companyCode

  if ($env:CGX_SAP_CONNECTION) { $conn = $env:CGX_SAP_CONNECTION } else { $conn = [string]$sys.connectionDescription }
  if ($env:CGX_SAP_CLIENT) { $client = $env:CGX_SAP_CLIENT } else { $client = [string]$sys.client }
  if ($env:CGX_SAP_USER) { $user = $env:CGX_SAP_USER } else { $user = [string]$sys.user }
  if ($env:CGX_SAP_LANGUAGE) { $lang = $env:CGX_SAP_LANGUAGE } else { $lang = [string]$sys.language }
  if ($env:CGX_CC) { $bukrs = $env:CGX_CC } else { $bukrs = [string]$cc.bukrs }

  Write-Status -Message ("Connection : {0}" -f $conn)
  Write-Status -Message ("Client/User: {0} / {1} / {2}" -f $client, $user, $lang)
  if ($VerifyOnly) {
    Write-Status -Message 'Mode       : VERIFY'
  } else {
    Write-Status -Message 'Mode       : CREATE (real SAP write)'
  }
  Write-Status -Message 'Truth      : Browser Cognixa cannot write T001 - this agent can.'

  $sapOk = $false
  try {
    $gui = [Runtime.InteropServices.Marshal]::GetActiveObject('SAPGUI')
    if ($gui) { $sapOk = $true }
  } catch {
    try {
      $gui = New-Object -ComObject 'Sapgui.ScriptingCtrl.1'
      if ($gui) { $sapOk = $true }
    } catch {
      $sapOk = $false
    }
  }

  if (-not $sapOk) {
    Write-Status -Message 'SAP GUI Scripting COM not found yet. Will still try via VBS if SAP Logon is installed.' -Color Yellow
    Write-Status -Message 'Enable: SAP GUI Options -> Scripting ON, and RZ11 sapgui/user_scripting=TRUE' -Color Yellow
  } else {
    Write-Status -Message 'SAP GUI Scripting COM is available.' -Color Green
  }

  if (-not $Password) {
    if ($env:CGX_SAP_PASSWORD) {
      $Password = ConvertTo-SecureString $env:CGX_SAP_PASSWORD -AsPlainText -Force
      Write-Status -Message 'Using password from CGX_SAP_PASSWORD env (session only).' -Color DarkYellow
    } else {
      Write-Status -Message 'Waiting for SAP password prompt...' -Color Cyan
      $prompt = 'SAP GUI password for {0} (not saved)' -f $user
      $Password = Read-Host -Prompt $prompt -AsSecureString
    }
  }

  $bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($Password)
  try {
    $plain = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)
  } finally {
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr) | Out-Null
  }

  if ([string]::IsNullOrWhiteSpace($plain)) {
    throw 'Password is required to log on to SAP GUI. Re-run run.cmd and enter the password when prompted.'
  }

  if ($VerifyOnly) { $mode = 'verify' } else { $mode = 'create' }
  Write-Status -Message ("Launching Create-CGX1.vbs mode={0} ..." -f $mode) -Color Cyan

  # Build args without embedding secrets in a single interpolated command string beyond process args.
  $argList = New-Object System.Collections.Generic.List[string]
  [void]$argList.Add('//nologo')
  [void]$argList.Add('"' + $vbsPath + '"')
  [void]$argList.Add('"' + $conn + '"')
  [void]$argList.Add('"' + $client + '"')
  [void]$argList.Add('"' + $user + '"')
  [void]$argList.Add('"' + $plain + '"')
  [void]$argList.Add('"' + $lang + '"')
  [void]$argList.Add('"' + $bukrs + '"')
  [void]$argList.Add('"' + ([string]$cc.butxt) + '"')
  [void]$argList.Add('"' + ([string]$cc.ort01) + '"')
  [void]$argList.Add('"' + ([string]$cc.land1) + '"')
  [void]$argList.Add('"' + ([string]$cc.waers) + '"')
  [void]$argList.Add('"' + ([string]$cc.spras) + '"')
  [void]$argList.Add('"' + $mode + '"')

  $psi = New-Object System.Diagnostics.ProcessStartInfo
  $psi.FileName = 'cscript.exe'
  $psi.Arguments = [string]::Join(' ', $argList)
  $psi.RedirectStandardOutput = $true
  $psi.RedirectStandardError = $true
  $psi.UseShellExecute = $false
  $psi.CreateNoWindow = $true

  $proc = New-Object System.Diagnostics.Process
  $proc.StartInfo = $psi
  [void]$proc.Start()
  $stdout = $proc.StandardOutput.ReadToEnd()
  $stderr = $proc.StandardError.ReadToEnd()
  [void]$proc.WaitForExit()
  $plain = $null
  [GC]::Collect()

  if ($stdout) { Write-Host $stdout.TrimEnd() }
  if ($stderr) { Write-Host $stderr.TrimEnd() -ForegroundColor DarkYellow }

  $code = [int]$proc.ExitCode
  if ($code -eq 0) {
    Write-Status -Message ("SUCCESS - check OX02 / SE16N T001 for {0}" -f $bukrs) -Color Green
  } elseif ($code -eq 1) {
    Write-Status -Message ("VERIFY - {0} not found (expected before first create)" -f $bukrs) -Color Yellow
  } elseif ($code -eq 7) {
    Write-Status -Message 'PARTIAL - confirm transport popup in SAP GUI, then re-run with -VerifyOnly' -Color Yellow
  } else {
    Write-Status -Message ("FAILED (exit {0}). See README for scripting prerequisites / field-ID re-record." -f $code) -Color Red
  }

  Write-Status -Message 'Preferred bulk path remains BC Sets (SCPR20) + CTS. This agent is residual.' -Color DarkGray
  exit $code
}
catch {
  Write-Status -Message ("ERROR: {0}" -f $_.Exception.Message) -Color Red
  Write-Status -Message 'Fix: Extract All zip -> open extracted folder -> double-click run.cmd' -Color Yellow
  Write-Status -Message 'Also need SAP GUI for Windows + scripting enabled.' -Color Yellow
  exit 10
}
