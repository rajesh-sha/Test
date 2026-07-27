# Cognixa - BC Set + CTS automation checklist runner (ASCII / PS5 safe)
# This does not invent an RFC library. It prepares evidence and next commands
# for SCPR20 / SCPR_ACTIVATE_BCSETS_REMOTE + CTS.
[CmdletBinding()]
param(
  [switch]$SkipPause
)

$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$log = Join-Path $here 'bcset-run.log'
$payloadPath = Join-Path $here 'payload.json'
$defPath = Join-Path $here 'bcset-definition.json'

function Write-Status([string]$Message, [string]$Color = 'White') {
  $line = '[{0}] {1}' -f (Get-Date -Format 'HH:mm:ss'), $Message
  Write-Host $line -ForegroundColor $Color
  Add-Content -LiteralPath $log -Value $line -Encoding ASCII
}

'Cognixa BC Set automation log' | Set-Content -LiteralPath $log -Encoding ASCII

try {
  Write-Status 'Preferred path: BC Sets (SCPR20) + CTS - not SAP GUI OX02 bot' Cyan
  if (-not (Test-Path $payloadPath)) { throw 'Missing payload.json' }
  if (-not (Test-Path $defPath)) { throw 'Missing bcset-definition.json' }

  $p = Get-Content -LiteralPath $payloadPath -Raw -Encoding UTF8 | ConvertFrom-Json
  $d = Get-Content -LiteralPath $defPath -Raw -Encoding UTF8 | ConvertFrom-Json

  Write-Status ('Playbook : {0}' -f $p.playbook)
  Write-Status ('BC Set   : {0}' -f $p.bcSet.id)
  Write-Status ('Company  : {0} / {1}' -f $p.companyCode.bukrs, $p.companyCode.butxt)
  Write-Status ('System   : {0} client {1}' -f $p.system.sid, $p.system.client)
  Write-Status ('Activate : {0}' -f $p.automation.activateApi)

  Write-Host ''
  Write-Host '=== AUTOMATION EXAMPLE (do in SAP) ===' -ForegroundColor Yellow
  Write-Host '1) ONE-TIME CREATE BC SET' -ForegroundColor Yellow
  Write-Host ('   - Follow Create-BCSet-in-SCPR20.md for {0}' -f $p.bcSet.id)
  Write-Host ('   - Values: {0}' -f ($d.objects[0].rows[0] | ConvertTo-Json -Compress))
  Write-Host ''
  Write-Host '2) ACTIVATE (automated preferred)' -ForegroundColor Yellow
  Write-Host '   A) Install/run ZCGX_ACTIVATE_BCSET.abap in A4H' -ForegroundColor Yellow
  Write-Host ('      PARAMETERS: p_bcset = {0}' -f $p.bcSet.id) -ForegroundColor Yellow
  Write-Host '   B) Or SCPR20 -> Enter BC Set -> Activate -> customizing TR' -ForegroundColor Yellow
  Write-Host ''
  Write-Host '3) CTS PIPELINE' -ForegroundColor Yellow
  Write-Host '   SE09 release customizing TR -> STMS import QAS -> (ALM gate) -> PRD' -ForegroundColor Yellow
  Write-Host ''
  Write-Host '4) VERIFY' -ForegroundColor Yellow
  Write-Host ('   OX02 or SE16N {0} = {1}' -f $p.verify.table, $p.verify.key) -ForegroundColor Yellow
  Write-Host ''

  $evidence = [ordered]@{
    atUtc = (Get-Date).ToUniversalTime().ToString('o')
    playbook = $p.playbook
    bcSetId = $p.bcSet.id
    companyCode = $p.companyCode.bukrs
    activateApi = $p.automation.activateApi
    steps = @(
      'Ensure BC Set exists (Create-BCSet-in-SCPR20.md)',
      'Activate via SCPR_ACTIVATE_BCSETS_REMOTE or SCPR20',
      'Release customizing transport SE09',
      'Import STMS to QAS/PRD',
      'Verify T001/OX02'
    )
    rank = '1 - preferred over SAP GUI residual bot'
  }
  $evPath = Join-Path $here 'evidence-plan.json'
  ($evidence | ConvertTo-Json -Depth 6) | Set-Content -LiteralPath $evPath -Encoding UTF8
  Write-Status ('Wrote {0}' -f $evPath) Green
  Write-Status 'This runner prepared the automation plan. Execute activate/CTS inside SAP (ABAP or SCPR20).' Cyan
  Write-Status 'GUI OX02 bot remains last resort only.' DarkGray
  exit 0
}
catch {
  Write-Status ('ERROR: {0}' -f $_.Exception.Message) Red
  exit 10
}
finally {
  if (-not $SkipPause) {
    Write-Host ''
    Write-Host 'Press ENTER to close...'
    [void](Read-Host)
  }
}
