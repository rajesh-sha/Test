# Cognixa Desktop Agent - create or verify company code CGX1 on A4H via SAP GUI Scripting.
# ASCII-only (Windows PowerShell 5.x safe). Run via run.cmd after Extract All.
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

'Cognixa Desktop Agent log' | Set-Content -LiteralPath $logPath -Encoding ASCII

function Write-Status {
  param(
    [Parameter(Mandatory = $true)][string]$Message,
    [string]$Color = 'White'
  )
  $ts = Get-Date -Format 'HH:mm:ss'
  $line = '[{0}] {1}' -f $ts, $Message
  Write-Host $line -ForegroundColor $Color
  Add-Content -LiteralPath $logPath -Value $line -Encoding ASCII
}

function Test-IsAdmin {
  try {
    $id = [Security.Principal.WindowsIdentity]::GetCurrent()
    $p = New-Object Security.Principal.WindowsPrincipal($id)
    return $p.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
  } catch { return $false }
}

function Get-SapSessionInfo {
  # Prefer VBS GetObject("SAPGUI") - same path Create-CGX1.vbs uses.
  # 64-bit PowerShell GetActiveObject often cannot see 32-bit SAP GUI (shows 0
  # sessions even when Easy Access is open). run.cmd forces 32-bit PS.
  $info = [ordered]@{ Sessions = 0; Connections = 0; Ok = $false; Detail = ''; Method = '' }

  $detectVbs = Join-Path $here 'Detect-SapSessions.vbs'
  if (Test-Path -LiteralPath $detectVbs) {
    try {
      $raw = (& cscript.exe //nologo $detectVbs 2>&1 | Out-String).Trim()
      if ($raw -match '(?m)^OK\|(\d+)\|(\d+)') {
        $info.Connections = [int]$Matches[1]
        $info.Sessions = [int]$Matches[2]
        $info.Ok = $true
        $info.Method = 'VBS-GetObject'
        $info.Detail = ('VBS GetObject OK; connections={0}; sessions={1}; ps={2}-bit' -f $info.Connections, $info.Sessions, ([IntPtr]::Size * 8))
        return $info
      }
      if ($raw -match '(?m)^SESSION\|') {
        $info.Sessions = ([regex]::Matches($raw, '(?m)^SESSION\|')).Count
        $info.Connections = 1
        $info.Ok = $true
        $info.Method = 'VBS-GetObject'
        $info.Detail = ('VBS GetObject OK (SESSION lines); sessions={0}; ps={1}-bit' -f $info.Sessions, ([IntPtr]::Size * 8))
        return $info
      }
      $info.Detail = ('VBS detect: {0}' -f (($raw -split "`n") | Select-Object -First 3) -join ' | ')
    } catch {
      $info.Detail = ('VBS detect failed: {0}' -f $_.Exception.Message)
    }
  }

  # Fallback: PowerShell GetActiveObject (works reliably in 32-bit PS)
  try {
    $gui = [Runtime.InteropServices.Marshal]::GetActiveObject('SAPGUI')
    $engine = $gui.GetScriptingEngine
    if (-not $engine) { $engine = $gui.GetScriptingEngine() }
    $connCount = 0
    try { $connCount = [int]$engine.Children.Count } catch { $connCount = 0 }
    $info.Connections = $connCount
    $sess = 0
    for ($i = 0; $i -lt $connCount; $i++) {
      try {
        $c = $null
        try { $c = $engine.Children.Item($i) } catch { $c = $engine.Children($i) }
        if ($c) {
          try { $sess += [int]$c.Children.Count } catch {}
        }
      } catch {}
    }
    $info.Sessions = $sess
    $info.Ok = $true
    $info.Method = 'PS-GetActiveObject'
    $info.Detail = ('GetActiveObject OK; connections={0}; sessions={1}; ps={2}-bit' -f $connCount, $sess, ([IntPtr]::Size * 8))
  } catch {
    $prev = $info.Detail
    $info.Detail = ('{0} | GetActiveObject failed: {1} | ps={2}-bit' -f $prev, $_.Exception.Message, ([IntPtr]::Size * 8)).Trim(' ','|')
  }
  return $info
}

try {
  Write-Status -Message 'Cognixa Desktop Agent starting...' -Color Cyan
  Write-Status -Message ('Folder: {0}' -f $here)

  if (Test-IsAdmin) {
    Write-Host ''
    Write-Host 'ERROR: Running as Administrator.' -ForegroundColor Red
    Write-Host 'SAP Easy Access is a normal-user window. Admin COM cannot see it (0 sessions).' -ForegroundColor Red
    Write-Host 'Close this window. Double-click run.cmd WITHOUT "Run as administrator".' -ForegroundColor Yellow
    Write-Host 'Keep SAP Easy Access open.' -ForegroundColor Yellow
    Write-Host ''
    throw 'Agent must NOT run as Administrator when SAP GUI is a normal user process.'
  }

  if ($here -match '(?i)\\AppData\\Local\\Temp\\|\\.zip($|\\)') {
    throw 'Running from a temp/zip path. Extract All the zip to a normal folder, then run run.cmd.'
  }
  if (-not (Test-Path -LiteralPath $payloadPath)) { throw 'Missing payload.json. Extract the full zip.' }
  if (-not (Test-Path -LiteralPath $vbsPath)) { throw 'Missing Create-CGX1.vbs. Extract the full zip.' }
  if (-not (Get-Command cscript.exe -ErrorAction SilentlyContinue)) {
    throw 'cscript.exe not found. Windows Script Host is required.'
  }

  $payload = Get-Content -LiteralPath $payloadPath -Raw -Encoding UTF8 | ConvertFrom-Json
  $sys = $payload.system
  $cc = $payload.companyCode

  if ($env:CGX_SAP_CONNECTION) { $conn = $env:CGX_SAP_CONNECTION } else { $conn = [string]$sys.connectionDescription }
  if ($env:CGX_SAP_CLIENT) { $client = $env:CGX_SAP_CLIENT } else { $client = [string]$sys.client }
  if ($env:CGX_SAP_USER) { $user = $env:CGX_SAP_USER } else { $user = [string]$sys.user }
  if ($env:CGX_SAP_LANGUAGE) { $lang = $env:CGX_SAP_LANGUAGE } else { $lang = [string]$sys.language }
  if ($env:CGX_CC) { $bukrs = $env:CGX_CC } else { $bukrs = [string]$cc.bukrs }

  Write-Status -Message ('Connection : {0}' -f $conn)
  Write-Status -Message ('Client/User: {0} / {1} / {2}' -f $client, $user, $lang)
  if ($VerifyOnly) { Write-Status -Message 'Mode       : VERIFY' } else { Write-Status -Message 'Mode       : CREATE (real SAP write)' }

  Write-Host ''
  Write-Host '============================================================' -ForegroundColor Yellow
  Write-Host ' REQUIRED BEFORE CREATE (this avoids the OpenConnection hang)' -ForegroundColor Yellow
  Write-Host ' 1. Open SAP Logon' -ForegroundColor Yellow
  Write-Host (' 2. Connect: {0}' -f $conn) -ForegroundColor Yellow
  Write-Host (' 3. Log on: client {0} / user {1} / lang {2}' -f $client, $user, $lang) -ForegroundColor Yellow
  Write-Host ' 4. Leave that SAP session open (Easy Access is fine)' -ForegroundColor Yellow
  Write-Host ' 5. Accept any "A script is trying to access SAP GUI" prompt' -ForegroundColor Yellow
  Write-Host ' 6. Do NOT run this agent as Administrator' -ForegroundColor Yellow
  Write-Host '============================================================' -ForegroundColor Yellow
  Write-Host ''

  $sapInfo = Get-SapSessionInfo
  Write-Status -Message ('SAP detect: {0}' -f $sapInfo.Detail)
  Write-Status -Message ('Current SAP GUI sessions detected: {0}' -f $sapInfo.Sessions)
  if ([int]$sapInfo.Sessions -lt 1) {
    Write-Host ''
    Write-Host 'No SCRIPTABLE SAP session detected (Easy Access can be open and still show 0).' -ForegroundColor Yellow
    Write-Host 'Do these in order:' -ForegroundColor Yellow
    Write-Host '  A) This window must NOT be Administrator' -ForegroundColor Yellow
    Write-Host '  B) In SAP GUI: Alt+F12 -> Options -> Accessibility & Scripting' -ForegroundColor Yellow
    Write-Host '     -> Enable scripting = ON  (untick "Notify when script attaches" if it blocks)' -ForegroundColor Yellow
    Write-Host '  C) FULLY close SAP Logon + Easy Access, then log on again' -ForegroundColor Yellow
    Write-Host '  D) Optional: run diagnose.cmd in this folder for details' -ForegroundColor Yellow
    Write-Host ''
    Write-Host 'IMPORTANT: at the next prompt press ENTER only. Do NOT type your password here.' -ForegroundColor Cyan
    [void](Read-Host 'Press ENTER only after scripting is ON and you re-logged on to SAP')
    $sapInfo = Get-SapSessionInfo
    Write-Status -Message ('SAP detect after wait: {0}' -f $sapInfo.Detail)
    Write-Status -Message ('SAP GUI sessions after wait: {0}' -f $sapInfo.Sessions)
    if ([int]$sapInfo.Sessions -lt 1) {
      throw 'Still 0 scriptable SAP sessions. Run diagnose.cmd. Typical fix: enable SAP GUI scripting, fully restart SAP Logon, re-logon, then run.cmd (not as Admin).'
    }
  } else {
    Write-Status -Message 'Existing SAP session found - will ATTACH (no OpenConnection).' -Color Green
  }

  if (-not $Password) {
    if ($env:CGX_SAP_PASSWORD) {
      $Password = ConvertTo-SecureString $env:CGX_SAP_PASSWORD -AsPlainText -Force
      Write-Status -Message 'Using password from CGX_SAP_PASSWORD env (session only).' -Color DarkYellow
    } else {
      Write-Host 'Password is only needed if SAP is still on the logon screen.' -ForegroundColor DarkGray
      Write-Host '>>> Type password (or just press ENTER if already logged on) <<<' -ForegroundColor Yellow
      $prompt = 'SAP GUI password for {0} (optional if already logged on)' -f $user
      $Password = Read-Host -Prompt $prompt -AsSecureString
    }
  }

  $bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($Password)
  try { $plain = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr) }
  finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr) | Out-Null }
  if ([string]::IsNullOrWhiteSpace($plain)) { $plain = 'NOT_USED' }

  if ($VerifyOnly) { $mode = 'verify' } else { $mode = 'create' }
  $openMode = 'attach'
  if ($env:CGX_SAP_OPEN_MODE) { $openMode = $env:CGX_SAP_OPEN_MODE }

  Write-Status -Message ('Launching Create-CGX1.vbs mode={0} openMode={1}' -f $mode, $openMode) -Color Cyan

  $argList = @(
    '//nologo',
    '"' + $vbsPath + '"',
    '"' + $conn + '"',
    '"' + $client + '"',
    '"' + $user + '"',
    '"' + $plain + '"',
    '"' + $lang + '"',
    '"' + $bukrs + '"',
    '"' + ([string]$cc.butxt) + '"',
    '"' + ([string]$cc.ort01) + '"',
    '"' + ([string]$cc.land1) + '"',
    '"' + ([string]$cc.waers) + '"',
    '"' + ([string]$cc.spras) + '"',
    '"' + $mode + '"',
    '"' + $openMode + '"'
  )

  $psi = New-Object System.Diagnostics.ProcessStartInfo
  $psi.FileName = 'cscript.exe'
  $psi.Arguments = [string]::Join(' ', $argList)
  $psi.RedirectStandardOutput = $true
  $psi.RedirectStandardError = $true
  $psi.UseShellExecute = $false
  $psi.CreateNoWindow = $true

  $proc = New-Object System.Diagnostics.Process
  $proc.StartInfo = $psi

  # MessageData keeps log path visible inside PS5.1 event actions
  $outEvent = Register-ObjectEvent -InputObject $proc -EventName OutputDataReceived -MessageData $logPath -Action {
    $line = $Event.SourceEventArgs.Data
    if ($line) {
      [Console]::Out.WriteLine($line)
      Add-Content -LiteralPath ([string]$Event.MessageData) -Value $line -Encoding ASCII
    }
  }
  $errEvent = Register-ObjectEvent -InputObject $proc -EventName ErrorDataReceived -MessageData $logPath -Action {
    $line = $Event.SourceEventArgs.Data
    if ($line) {
      [Console]::Error.WriteLine($line)
      Add-Content -LiteralPath ([string]$Event.MessageData) -Value $line -Encoding ASCII
    }
  }

  Write-Status -Message 'Starting cscript (attach mode). Watch for STEP| lines...' -Color Cyan
  [void]$proc.Start()
  $proc.BeginOutputReadLine()
  $proc.BeginErrorReadLine()

  $deadline = (Get-Date).AddSeconds(90)
  $lastBeat = Get-Date
  while (-not $proc.HasExited) {
    if ((Get-Date) -gt $deadline) {
      try { $proc.Kill() } catch {}
      throw 'Timed out after 90s in SAP GUI Scripting. Click the SAP GUI window and Allow scripting / handle popups, then re-run. Prefer: log on in SAP first (attach mode).'
    }
    if (((Get-Date) - $lastBeat).TotalSeconds -ge 5) {
      Write-Status -Message 'Still running... check SAP GUI for Allow/script/transport popups.' -Color DarkYellow
      $lastBeat = Get-Date
    }
    Start-Sleep -Milliseconds 300
  }
  Start-Sleep -Milliseconds 500
  Unregister-Event -SourceIdentifier $outEvent.Name -ErrorAction SilentlyContinue
  Unregister-Event -SourceIdentifier $errEvent.Name -ErrorAction SilentlyContinue

  $plain = $null
  [GC]::Collect()

  $code = [int]$proc.ExitCode
  if ($code -eq 0) {
    Write-Status -Message ('SUCCESS - check OX02 / SE16N T001 for {0}' -f $bukrs) -Color Green
  } elseif ($code -eq 1) {
    Write-Status -Message ('VERIFY - {0} not found (expected before first create)' -f $bukrs) -Color Yellow
  } elseif ($code -eq 4) {
    Write-Status -Message 'NO_SESSION - log on in SAP GUI first, leave session open, re-run.' -Color Red
  } elseif ($code -eq 7) {
    Write-Status -Message 'PARTIAL - confirm transport popup in SAP GUI, then verify OX02.' -Color Yellow
  } else {
    Write-Status -Message ('FINISHED with exit {0}. See STEP/ERROR lines above.' -f $code) -Color Red
  }
  exit $code
}
catch {
  Write-Status -Message ('ERROR: {0}' -f $_.Exception.Message) -Color Red
  Write-Status -Message 'Fix path: SAP Logon -> log on -> leave open -> Extracted folder -> run.cmd' -Color Yellow
  exit 10
}
