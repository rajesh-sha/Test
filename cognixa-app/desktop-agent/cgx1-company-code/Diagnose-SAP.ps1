# Cognixa Desktop Agent - diagnose why SAP sessions = 0
# ASCII-only. Run via diagnose.cmd (NOT as Administrator).
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
Out ('Elevated Admin?')

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
    Out ('  {0} pid={1}' -f $pr.ProcessName, $pr.Id) Green
  }
}

Out ''
Out 'SAP GUI scripting registry (HKCU):'
$regPath = 'HKCU:\Software\SAP\SAPGUI Front\SAP Frontend Server\Security'
try {
  if (Test-Path $regPath) {
    $props = Get-ItemProperty -Path $regPath -ErrorAction SilentlyContinue
    $userScripting = $props.UserScripting
    $warn = $props.WarnOnAttach
    $warnAction = $props.WarnOnAttachment
    Out ('  UserScripting = {0}  (1 means enabled)' -f $userScripting)
    Out ('  WarnOnAttach  = {0}' -f $warn)
    if ($userScripting -ne 1) {
      Out '  Scripting looks DISABLED. Enable in SAP GUI Options -> Accessibility & Scripting,' Yellow
      Out '  then FULLY close SAP Logon/GUI and log on again.' Yellow
    }
  } else {
    Out ('  Key not found: {0}' -f $regPath) Yellow
  }
} catch {
  Out ('  Registry read failed: {0}' -f $_.Exception.Message) Yellow
}

Out ''
Out 'COM GetActiveObject(SAPGUI):'
$sessionTotal = 0
$connTotal = 0
try {
  $gui = [Runtime.InteropServices.Marshal]::GetActiveObject('SAPGUI')
  Out '  GetActiveObject OK' Green
  $engine = $null
  try { $engine = $gui.GetScriptingEngine } catch { try { $engine = $gui.GetScriptingEngine() } catch {} }
  if (-not $engine) {
    Out '  GetScriptingEngine FAILED (scripting disabled or blocked).' Red
  } else {
    try { $connTotal = [int]$engine.Children.Count } catch { $connTotal = 0 }
    Out ('  Connections visible to scripting: {0}' -f $connTotal)
    for ($i = 0; $i -lt $connTotal; $i++) {
      $c = $null
      try { $c = $engine.Children.Item($i) } catch { try { $c = $engine.Children($i) } catch {} }
      $sc = 0
      if ($c) { try { $sc = [int]$c.Children.Count } catch { $sc = 0 } }
      $sessionTotal += $sc
      Out ('    connection[{0}] sessions={1}' -f $i, $sc)
    }
  }
} catch {
  Out ('  FAILED: {0}' -f $_.Exception.Message) Red
  Out '  If SAP is open: enable scripting, close SAP completely, log on again, re-run diagnose (non-Admin).' Yellow
}

Out ''
Out ('RESULT: scriptable sessions = {0}' -f $sessionTotal)
if ($sessionTotal -gt 0) {
  Out 'OK - run.cmd should be able to attach now.' Green
} else {
  Out 'NOT OK - run.cmd will fail with 0 sessions until this is fixed.' Red
  Out 'Checklist:' Yellow
  Out '  1) Not running as Administrator' Yellow
  Out '  2) SAP Easy Access is open (classic SAP GUI for Windows)' Yellow
  Out '  3) Options -> Accessibility & Scripting -> Enable scripting = ON' Yellow
  Out '  4) Fully close SAP Logon + all GUI windows, then log on again' Yellow
  Out '  5) Re-run diagnose.cmd (expect sessions >= 1), then run.cmd' Yellow
}
Out ''
Out ('Wrote {0}' -f $log) Cyan
