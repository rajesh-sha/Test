# Cognixa Desktop Agent - diagnose why SAP sessions = 0
# ASCII-only. Run via diagnose.cmd (NOT as Administrator). Prefer 32-bit PowerShell.
$ErrorActionPreference = 'Continue'
$log = Join-Path $PSScriptRoot 'diagnose.log'
'' | Set-Content -LiteralPath $log -Encoding ASCII

function Out([string]$m, [string]$c = 'White') {
  Write-Host $m -ForegroundColor $c
  Add-Content -LiteralPath $log -Value $m -Encoding ASCII
}

Out '=== Cognixa SAP GUI diagnose ===' Cyan
Out ('Time   : {0}' -f (Get-Date -Format o))
Out ('Folder : {0}' -f $PSScriptRoot)
Out ('User   : {0}' -f $env:USERNAME)
Out ('PS bitness: {0}-bit' -f [IntPtr]::Size * 8)
if ([IntPtr]::Size -eq 8) {
  Out '  WARNING: 64-bit PowerShell often cannot see 32-bit SAP GUI sessions.' Yellow
  Out '  diagnose.cmd / run.cmd should relaunch as 32-bit automatically.' Yellow
}

Out 'Elevated Admin?'
$isAdmin = $false
try {
  $id = [Security.Principal.WindowsIdentity]::GetCurrent()
  $p = New-Object Security.Principal.WindowsPrincipal($id)
  $isAdmin = $p.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
} catch {}
if ($isAdmin) {
  Out '  YES - THIS IS THE PROBLEM. Admin cannot see normal-user SAP GUI.' Red
  Out '  Close this window. Double-click diagnose.cmd / run.cmd WITHOUT Run as administrator.' Yellow
} else {
  Out '  No (good)' Green
}

Out ''
Out 'SAP-related processes:'
$procs = Get-Process -ErrorAction SilentlyContinue | Where-Object { $_.ProcessName -match '^(saplogon|sapgui|saplgpad|sapguiserver|nwbc)$' }
if (-not $procs) {
  Out '  NONE found. Open SAP Logon and log on first.' Red
} else {
  foreach ($pr in $procs) {
    $bit = '?'
    try {
      $path = $pr.Path
      if ($path) {
        # Heuristic: SysWOW64 / Program Files (x86) => 32-bit GUI
        if ($path -match '(?i)SysWOW64|Program Files \(x86\)| sap\\front') { $bit = 'likely-32bit' } else { $bit = 'check-path' }
        Out ('  {0} pid={1} ({2}) {3}' -f $pr.ProcessName, $pr.Id, $bit, $path) Green
      } else {
        Out ('  {0} pid={1}' -f $pr.ProcessName, $pr.Id) Green
      }
    } catch {
      Out ('  {0} pid={1}' -f $pr.ProcessName, $pr.Id) Green
    }
  }
}

Out ''
Out 'SAP GUI scripting registry (HKCU):'
$regPath = 'HKCU:\Software\SAP\SAPGUI Front\SAP Frontend Server\Security'
try {
  if (-not (Test-Path $regPath)) {
    New-Item -Path $regPath -Force | Out-Null
  }
  $props = Get-ItemProperty -Path $regPath -ErrorAction SilentlyContinue
  $userScripting = $props.UserScripting
  $warn = $props.WarnOnAttach
  Out ('  UserScripting = {0}  (1 means enabled)' -f $userScripting)
  Out ('  WarnOnAttach  = {0}' -f $warn)
  if ($userScripting -ne 1) {
    Out '  Enabling UserScripting=1 in registry now...' Yellow
    New-ItemProperty -Path $regPath -Name 'UserScripting' -PropertyType DWord -Value 1 -Force | Out-Null
    # Reduce attach friction for demos (user can re-enable warn)
    New-ItemProperty -Path $regPath -Name 'WarnOnAttach' -PropertyType DWord -Value 0 -Force | Out-Null
    Out '  Set UserScripting=1 and WarnOnAttach=0.' Green
    Out '  You MUST fully close SAP Logon + Easy Access, then log on again for this to take effect.' Yellow
  }
} catch {
  Out ('  Registry update failed: {0}' -f $_.Exception.Message) Yellow
}

Out ''
Out 'Method A - VBS GetObject(SAPGUI) [preferred]:'
$sessionTotal = 0
$connTotal = 0
$vbs = Join-Path $PSScriptRoot 'Detect-SapSessions.vbs'
if (Test-Path -LiteralPath $vbs) {
  try {
    $lines = @(& cscript.exe //nologo $vbs 2>&1 | ForEach-Object { "$_" })
    foreach ($ln in $lines) {
      if ($ln -and $ln.Trim()) { Out ('  {0}' -f $ln.Trim()) }
    }
    $joined = ($lines -join "`n")
    if ($joined -match '(?m)^OK\|(\d+)\|(\d+)') {
      $connTotal = [int]$Matches[1]
      $sessionTotal = [int]$Matches[2]
    } elseif ($joined -match '(?m)^SESSION\|') {
      $sessionTotal = ([regex]::Matches($joined, '(?m)^SESSION\|')).Count
      $connTotal = 1
    }
  } catch {
    Out ('  VBS detect failed: {0}' -f $_.Exception.Message) Red
  }
} else {
  Out '  Detect-SapSessions.vbs missing' Red
}

Out ''
Out 'Method B - PowerShell GetActiveObject(SAPGUI):'
try {
  $gui = [Runtime.InteropServices.Marshal]::GetActiveObject('SAPGUI')
  Out '  GetActiveObject OK' Green
  $engine = $null
  try { $engine = $gui.GetScriptingEngine } catch { try { $engine = $gui.GetScriptingEngine() } catch {} }
  if (-not $engine) {
    Out '  GetScriptingEngine FAILED (scripting disabled or 64-bit PS vs 32-bit GUI).' Red
  } else {
    $c2 = 0; $s2 = 0
    try { $c2 = [int]$engine.Children.Count } catch { $c2 = 0 }
    for ($i = 0; $i -lt $c2; $i++) {
      $c = $null
      try { $c = $engine.Children.Item($i) } catch { try { $c = $engine.Children($i) } catch {} }
      $sc = 0
      if ($c) { try { $sc = [int]$c.Children.Count } catch { $sc = 0 } }
      $s2 += $sc
      Out ('    connection[{0}] sessions={1}' -f $i, $sc)
    }
    Out ('  PS connections={0} sessions={1}' -f $c2, $s2)
    if ($sessionTotal -lt 1 -and $s2 -gt 0) { $sessionTotal = $s2; $connTotal = $c2 }
  }
} catch {
  Out ('  FAILED: {0}' -f $_.Exception.Message) Red
}

Out ''
Out ('RESULT: scriptable sessions = {0} (connections={1})' -f $sessionTotal, $connTotal)
if ($sessionTotal -gt 0) {
  Out 'OK - run.cmd should be able to attach now.' Green
} else {
  Out 'NOT OK - run.cmd will fail with 0 sessions until this is fixed.' Red
  Out 'Checklist:' Yellow
  Out '  1) Not running as Administrator' Yellow
  Out '  2) Use diagnose.cmd / run.cmd (forces 32-bit PowerShell)' Yellow
  Out '  3) Classic SAP GUI for Windows open (not only browser / webgui)' Yellow
  Out '  4) Options -> Accessibility & Scripting -> Enable scripting = ON' Yellow
  Out '  5) Fully close SAP Logon + all GUI windows, then log on again' Yellow
  Out '  6) Accept any scripting access popup in SAP' Yellow
  Out '  7) Re-run diagnose.cmd (expect sessions >= 1), then run.cmd' Yellow
}
Out ''
Out ('Wrote {0}' -f $log) Cyan
