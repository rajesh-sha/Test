' Cognixa Desktop Agent - create/verify company code via OX02 (SAP GUI Scripting)
' ASCII-only. Invoked by Run-Create-CGX1.ps1.
' Args:
'  0 connName 1 client 2 user 3 pass 4 logonLang
'  5 bukrs 6 butxt 7 ort01 8 land1 9 waers 10 spras
'  11 mode: create | verify
'  12 optional: attach (default) | open
'
' IMPORTANT: Default mode ATTACHES to an already logged-on SAP GUI session.
' OpenConnection often hangs - log on manually in SAP GUI first.

Option Explicit

Dim connName, client, user, pass, lang, bukrs, butxt, ort01, land1, waers, spras, mode, openMode
Dim SapGuiAuto, application, connection, session
Dim i

If WScript.Arguments.Count < 12 Then
  WScript.Echo "ERROR|Usage: Create-CGX1.vbs ... <create|verify> [attach|open]"
  WScript.Quit 2
End If

connName = WScript.Arguments(0)
client   = WScript.Arguments(1)
user     = WScript.Arguments(2)
pass     = WScript.Arguments(3)
lang     = WScript.Arguments(4)
bukrs    = UCase(WScript.Arguments(5))
butxt    = WScript.Arguments(6)
ort01    = WScript.Arguments(7)
land1    = UCase(WScript.Arguments(8))
waers    = UCase(WScript.Arguments(9))
spras    = UCase(WScript.Arguments(10))
mode     = LCase(WScript.Arguments(11))
openMode = "attach"
If WScript.Arguments.Count >= 13 Then openMode = LCase(WScript.Arguments(12))

Sub Step(msg)
  WScript.Echo "STEP|" & msg
  WScript.StdOut.Write ""  ' encourage flush
End Sub

Step "VBS start mode=" & mode & " openMode=" & openMode
Step "Target company code=" & bukrs & " conn=" & connName

On Error Resume Next

Step "Getting SAPGUI object..."
Set SapGuiAuto = GetObject("SAPGUI")
If Err.Number <> 0 Or SapGuiAuto Is Nothing Then
  Err.Clear
  Step "GetObject(SAPGUI) failed - trying Sapgui.ScriptingCtrl.1"
  Set SapGuiAuto = CreateObject("Sapgui.ScriptingCtrl.1")
End If
If Err.Number <> 0 Or SapGuiAuto Is Nothing Then
  WScript.Echo "ERROR|SAP GUI Scripting engine not available. Open SAP Logon first and enable scripting."
  WScript.Quit 3
End If
Step "SAPGUI object OK"

Step "GetScriptingEngine..."
Set application = SapGuiAuto.GetScriptingEngine
If Err.Number <> 0 Or application Is Nothing Then
  WScript.Echo "ERROR|GetScriptingEngine failed. Enable scripting in SAP GUI options and RZ11 sapgui/user_scripting=TRUE."
  WScript.Quit 3
End If
Step "Scripting engine OK. Connections=" & application.Children.Count

If application.Children.Count > 0 Then
  Step "Attaching to existing connection(0)..."
  Set connection = application.Children(0)
ElseIf openMode = "open" Then
  Step "WARNING: OpenConnection can hang. Starting OpenConnection('" & connName & "')..."
  Set connection = application.OpenConnection(connName, True)
  Step "OpenConnection returned. Err=" & Err.Number
Else
  WScript.Echo "ERROR|NO_SESSION|No SAP GUI connection open."
  WScript.Echo "ERROR|Do this: open SAP Logon -> S4HANA2023 SHARED GUI -> log on client 800 / Rajesh1 -> leave the session open -> run run.cmd again."
  WScript.Quit 4
End If

If Err.Number <> 0 Or connection Is Nothing Then
  WScript.Echo "ERROR|Could not use connection '" & connName & "'. Err=" & Err.Description
  WScript.Quit 4
End If
Step "Connection OK. Sessions=" & connection.Children.Count

If connection.Children.Count > 0 Then
  Set session = connection.Children(0)
  Step "Attached session(0)"
Else
  WScript.Echo "ERROR|No SAP session on the connection. Log on fully in SAP GUI first."
  WScript.Quit 4
End If

' If still on logon screen, fill it
If HasId(session, "wnd[0]/usr/txtRSYST-MANDT") Then
  Step "Logon screen detected - filling client/user/password..."
  session.findById("wnd[0]/usr/txtRSYST-MANDT").text = client
  session.findById("wnd[0]/usr/txtRSYST-BNAME").text = user
  session.findById("wnd[0]/usr/pwdRSYST-BCODE").text = pass
  If HasId(session, "wnd[0]/usr/txtRSYST-LANGU") Then
    session.findById("wnd[0]/usr/txtRSYST-LANGU").text = lang
  End If
  session.findById("wnd[0]").sendVKey 0
  WScript.Sleep 1500
  DismissCommonPopups session
  Step "Logon send complete"
Else
  Step "Already logged on - skipping password logon screen"
End If

If Err.Number <> 0 Then
  WScript.Echo "ERROR|Logon failed: " & Err.Description
  WScript.Quit 5
End If

Step "Opening /nOX02 ..."
session.findById("wnd[0]/tbar[0]/okcd").text = "/nOX02"
session.findById("wnd[0]").sendVKey 0
WScript.Sleep 1000
DismissCommonPopups session
Step "OX02 opened (or attempted)"

If mode = "verify" Then
  If CompanyCodeVisible(session, bukrs) Then
    WScript.Echo "OK|FOUND|" & bukrs & "|Company code exists in OX02/T001"
    WScript.Quit 0
  Else
    WScript.Echo "OK|MISSING|" & bukrs & "|Company code not found - create it with mode=create"
    WScript.Quit 1
  End If
End If

If CompanyCodeVisible(session, bukrs) Then
  WScript.Echo "OK|EXISTS|" & bukrs & "|Already present - no write needed"
  WScript.Quit 0
End If

Step "Company code not found - pressing New Entries..."
Err.Clear
If HasId(session, "wnd[0]/tbar[1]/btn[5]") Then
  session.findById("wnd[0]/tbar[1]/btn[5]").press
ElseIf HasId(session, "wnd[0]/tbar[1]/btn[8]") Then
  session.findById("wnd[0]/tbar[1]/btn[8]").press
Else
  session.findById("wnd[0]").sendVKey 21
End If
WScript.Sleep 700
Step "Filling New Entries fields for " & bukrs

If Not FillNewEntry(session, bukrs, butxt, ort01, land1, waers, spras) Then
  WScript.Echo "ERROR|Could not fill New Entries fields. Re-record OX02 field IDs (see README)."
  WScript.Quit 6
End If
Step "Fields filled - pressing Save..."

Err.Clear
session.findById("wnd[0]/tbar[0]/btn[11]").press
WScript.Sleep 1000
DismissCommonPopups session

If HasId(session, "wnd[1]") Then
  On Error Resume Next
  Step "Popup detected after Save - try Continue / handle transport in SAP GUI"
  If HasId(session, "wnd[1]/tbar[0]/btn[0]") Then session.findById("wnd[1]/tbar[0]/btn[0]").press
  If HasId(session, "wnd[1]/tbar[0]/btn[11]") Then session.findById("wnd[1]/tbar[0]/btn[11]").press
  WScript.Sleep 600
End If

If HasId(session, "wnd[1]") Then
  WScript.Echo "WARN|Transport popup open - select/create customizing request in SAP GUI, then continue"
End If

Step "Re-opening OX02 to verify..."
session.findById("wnd[0]/tbar[0]/okcd").text = "/nOX02"
session.findById("wnd[0]").sendVKey 0
WScript.Sleep 800

If CompanyCodeVisible(session, bukrs) Then
  WScript.Echo "OK|CREATED|" & bukrs & "|Company code written - verify transport saved"
  WScript.Quit 0
Else
  WScript.Echo "WARN|SAVE_UNCONFIRMED|" & bukrs & "|Fill/save may need transport confirm or field-ID fix. Check OX02 manually."
  WScript.Quit 7
End If

Function HasId(sess, id)
  On Error Resume Next
  Dim o
  Set o = sess.findById(id, False)
  HasId = (Err.Number = 0 And Not o Is Nothing)
  Err.Clear
End Function

Sub DismissCommonPopups(sess)
  On Error Resume Next
  Dim guard
  guard = 0
  Do While guard < 5
    guard = guard + 1
    If HasId(sess, "wnd[1]/usr/radMULTI_LOGON_OPT2") Then
      sess.findById("wnd[1]/usr/radMULTI_LOGON_OPT2").select
      sess.findById("wnd[1]/tbar[0]/btn[0]").press
    ElseIf HasId(sess, "wnd[1]/tbar[0]/btn[0]") Then
      If InStr(1, LCase(sess.findById("wnd[1]").Text), "copyright") > 0 Or InStr(1, LCase(sess.findById("wnd[1]").Text), "license") > 0 Then
        sess.findById("wnd[1]/tbar[0]/btn[0]").press
      Else
        Exit Do
      End If
    Else
      Exit Do
    End If
    WScript.Sleep 400
  Loop
  Err.Clear
End Sub

Function CompanyCodeVisible(sess, code)
  On Error Resume Next
  CompanyCodeVisible = False
  Step "Position/search for " & code & " in OX02..."
  If HasId(sess, "wnd[0]/tbar[1]/btn[1]") Then
    sess.findById("wnd[0]/tbar[1]/btn[1]").press
    WScript.Sleep 400
  End If
  If HasId(sess, "wnd[1]/usr/txtV_T001-BUKRS") Then
    sess.findById("wnd[1]/usr/txtV_T001-BUKRS").text = code
    sess.findById("wnd[1]/tbar[0]/btn[0]").press
    WScript.Sleep 500
  ElseIf HasId(sess, "wnd[1]/usr/txtBUKRS") Then
    sess.findById("wnd[1]/usr/txtBUKRS").text = code
    sess.findById("wnd[1]/tbar[0]/btn[0]").press
    WScript.Sleep 500
  End If

  If CellEquals(sess, "wnd[0]/usr/tblSAPL0F00TVIEW/txtV_T001-BUKRS[0,0]", code) Then CompanyCodeVisible = True
  If CellEquals(sess, "wnd[0]/usr/tblSAPL0F00TVIEW/ctxtV_T001-BUKRS[0,0]", code) Then CompanyCodeVisible = True
  If CellEquals(sess, "wnd[0]/usr/tblSAPLSVCMTCTRL_V_T001/txtV_T001-BUKRS[0,0]", code) Then CompanyCodeVisible = True
  Err.Clear
End Function

Function CellEquals(sess, id, expected)
  On Error Resume Next
  Dim v
  CellEquals = False
  If Not HasId(sess, id) Then Exit Function
  v = UCase(Trim(sess.findById(id).text))
  If v = UCase(Trim(expected)) Then CellEquals = True
  Err.Clear
End Function

Function FillNewEntry(sess, bukrs, butxt, ort01, land1, waers, spras)
  On Error Resume Next
  FillNewEntry = False
  Dim ok
  ok = False

  If HasId(sess, "wnd[0]/usr/tblSAPL0F00TVIEW/txtV_T001-BUKRS[0,0]") Or HasId(sess, "wnd[0]/usr/tblSAPL0F00TVIEW/txtV_T001-BUKRS[0]") Then
    SetText sess, Array( _
      "wnd[0]/usr/tblSAPL0F00TVIEW/txtV_T001-BUKRS[0,0]", _
      "wnd[0]/usr/tblSAPL0F00TVIEW/txtV_T001-BUKRS[0]"), bukrs
    SetText sess, Array( _
      "wnd[0]/usr/tblSAPL0F00TVIEW/txtV_T001-BUTXT[0,0]", _
      "wnd[0]/usr/tblSAPL0F00TVIEW/txtV_T001-BUTXT[0]"), butxt
    SetText sess, Array( _
      "wnd[0]/usr/tblSAPL0F00TVIEW/txtV_T001-ORT01[0,0]", _
      "wnd[0]/usr/tblSAPL0F00TVIEW/txtV_T001-ORT01[0]"), ort01
    SetText sess, Array( _
      "wnd[0]/usr/tblSAPL0F00TVIEW/ctxtV_T001-LAND1[0,0]", _
      "wnd[0]/usr/tblSAPL0F00TVIEW/ctxtV_T001-LAND1[0]", _
      "wnd[0]/usr/tblSAPL0F00TVIEW/txtV_T001-LAND1[0,0]"), land1
    SetText sess, Array( _
      "wnd[0]/usr/tblSAPL0F00TVIEW/ctxtV_T001-WAERS[0,0]", _
      "wnd[0]/usr/tblSAPL0F00TVIEW/ctxtV_T001-WAERS[0]", _
      "wnd[0]/usr/tblSAPL0F00TVIEW/txtV_T001-WAERS[0,0]"), waers
    SetText sess, Array( _
      "wnd[0]/usr/tblSAPL0F00TVIEW/ctxtV_T001-SPRAS[0,0]", _
      "wnd[0]/usr/tblSAPL0F00TVIEW/ctxtV_T001-SPRAS[0]", _
      "wnd[0]/usr/tblSAPL0F00TVIEW/txtV_T001-SPRAS[0,0]"), spras
    ok = True
  End If

  If Not ok Then
    If HasId(sess, "wnd[0]/usr/txtV_T001-BUKRS") Then
      sess.findById("wnd[0]/usr/txtV_T001-BUKRS").text = bukrs
      If HasId(sess, "wnd[0]/usr/txtV_T001-BUTXT") Then sess.findById("wnd[0]/usr/txtV_T001-BUTXT").text = butxt
      If HasId(sess, "wnd[0]/usr/txtV_T001-ORT01") Then sess.findById("wnd[0]/usr/txtV_T001-ORT01").text = ort01
      If HasId(sess, "wnd[0]/usr/ctxtV_T001-LAND1") Then sess.findById("wnd[0]/usr/ctxtV_T001-LAND1").text = land1
      If HasId(sess, "wnd[0]/usr/ctxtV_T001-WAERS") Then sess.findById("wnd[0]/usr/ctxtV_T001-WAERS").text = waers
      If HasId(sess, "wnd[0]/usr/ctxtV_T001-SPRAS") Then sess.findById("wnd[0]/usr/ctxtV_T001-SPRAS").text = spras
      ok = True
    End If
  End If

  FillNewEntry = ok
  Err.Clear
End Function

Sub SetText(sess, ids, value)
  On Error Resume Next
  Dim i
  For i = 0 To UBound(ids)
    If HasId(sess, ids(i)) Then
      sess.findById(ids(i)).text = value
      Exit Sub
    End If
  Next
  Err.Clear
End Sub
