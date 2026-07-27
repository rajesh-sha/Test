' Cognixa Desktop Agent — create company code via OX02 (SAP GUI Scripting)
' Invoked by Run-Create-CGX1.ps1. Arguments (WScript.Arguments):
'   0 connection description
'   1 client
'   2 user
'   3 password
'   4 language
'   5 company code
'   6 company name
'   7 city
'   8 country
'   9 currency
'  10 language key (SPRAS)
'  11 mode: create | verify

Option Explicit

Dim connName, client, user, pass, lang, bukrs, butxt, ort01, land1, waers, spras, mode
Dim SapGuiAuto, application, connection, session
Dim i, found, rowCount, cellVal, errMsg

If WScript.Arguments.Count < 12 Then
  WScript.Echo "ERROR|Usage: Create-CGX1.vbs <conn> <client> <user> <pass> <logonLang> <bukrs> <butxt> <ort01> <land1> <waers> <spras> <create|verify>"
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

On Error Resume Next

Set SapGuiAuto = GetObject("SAPGUI")
If Err.Number <> 0 Or SapGuiAuto Is Nothing Then
  Err.Clear
  Set SapGuiAuto = CreateObject("Sapgui.ScriptingCtrl.1")
End If
If Err.Number <> 0 Or SapGuiAuto Is Nothing Then
  WScript.Echo "ERROR|SAP GUI Scripting engine not available. Open SAP Logon and enable scripting."
  WScript.Quit 3
End If

Set application = SapGuiAuto.GetScriptingEngine
If Err.Number <> 0 Or application Is Nothing Then
  WScript.Echo "ERROR|GetScriptingEngine failed. Enable scripting in SAP GUI options and RZ11 sapgui/user_scripting=TRUE."
  WScript.Quit 3
End If

' Prefer an existing connection; else open by description
If application.Children.Count > 0 Then
  Set connection = application.Children(0)
Else
  Set connection = application.OpenConnection(connName, True)
End If
If Err.Number <> 0 Or connection Is Nothing Then
  WScript.Echo "ERROR|Could not open connection '" & connName & "'. Check SAP Logon entry name."
  WScript.Quit 4
End If

If connection.Children.Count > 0 Then
  Set session = connection.Children(0)
Else
  WScript.Echo "ERROR|No SAP session after open."
  WScript.Quit 4
End If

' Logon screen if present
If HasId(session, "wnd[0]/usr/txtRSYST-MANDT") Then
  session.findById("wnd[0]/usr/txtRSYST-MANDT").text = client
  session.findById("wnd[0]/usr/txtRSYST-BNAME").text = user
  session.findById("wnd[0]/usr/pwdRSYST-BCODE").text = pass
  If HasId(session, "wnd[0]/usr/txtRSYST-LANGU") Then
    session.findById("wnd[0]/usr/txtRSYST-LANGU").text = lang
  End If
  session.findById("wnd[0]").sendVKey 0
  WScript.Sleep 1200
  ' license / multiple logon / copyright popups
  DismissCommonPopups session
End If

If Err.Number <> 0 Then
  WScript.Echo "ERROR|Logon failed: " & Err.Description
  WScript.Quit 5
End If

' Open OX02
session.findById("wnd[0]/tbar[0]/okcd").text = "/nOX02"
session.findById("wnd[0]").sendVKey 0
WScript.Sleep 800
DismissCommonPopups session

If mode = "verify" Then
  found = CompanyCodeVisible(session, bukrs)
  If found Then
    WScript.Echo "OK|FOUND|" & bukrs & "|Company code exists in OX02/T001"
    WScript.Quit 0
  Else
    WScript.Echo "OK|MISSING|" & bukrs & "|Company code not found — create it with mode=create"
    WScript.Quit 1
  End If
End If

' Already exists?
If CompanyCodeVisible(session, bukrs) Then
  WScript.Echo "OK|EXISTS|" & bukrs & "|Already present — no write needed"
  WScript.Quit 0
End If

' New Entries (toolbar btn varies; try common patterns)
Err.Clear
If HasId(session, "wnd[0]/tbar[1]/btn[5]") Then
  session.findById("wnd[0]/tbar[1]/btn[5]").press
ElseIf HasId(session, "wnd[0]/tbar[1]/btn[8]") Then
  session.findById("wnd[0]/tbar[1]/btn[8]").press
Else
  session.findById("wnd[0]").sendVKey 21 ' Ctrl+F5 often New Entries in view maintenance
End If
WScript.Sleep 600

If Not FillNewEntry(session, bukrs, butxt, ort01, land1, waers, spras) Then
  WScript.Echo "ERROR|Could not fill New Entries fields. Re-record OX02 field IDs (see README)."
  WScript.Quit 6
End If

' Save
Err.Clear
session.findById("wnd[0]/tbar[0]/btn[11]").press
WScript.Sleep 900
DismissCommonPopups session

' Address popup (optional) — continue
If HasId(session, "wnd[1]") Then
  On Error Resume Next
  If HasId(session, "wnd[1]/tbar[0]/btn[0]") Then session.findById("wnd[1]/tbar[0]/btn[0]").press
  If HasId(session, "wnd[1]/tbar[0]/btn[11]") Then session.findById("wnd[1]/tbar[0]/btn[11]").press
  WScript.Sleep 500
End If

' Transport request popup — leave for user if present, try Enter/Continue
If HasId(session, "wnd[1]") Then
  WScript.Echo "WARN|Transport popup open — select/create customizing request in SAP GUI, then continue"
  ' Do not auto-invent a transport; user must confirm
End If

WScript.Sleep 800
session.findById("wnd[0]/tbar[0]/okcd").text = "/nOX02"
session.findById("wnd[0]").sendVKey 0
WScript.Sleep 700

If CompanyCodeVisible(session, bukrs) Then
  WScript.Echo "OK|CREATED|" & bukrs & "|Company code written — verify transport saved"
  WScript.Quit 0
Else
  WScript.Echo "WARN|SAVE_UNCONFIRMED|" & bukrs & "|Fill/save may need transport confirm or field-ID fix. Check OX02 manually."
  WScript.Quit 7
End If

' ----------------- helpers -----------------

Function HasId(sess, id)
  On Error Resume Next
  Dim o
  Set o = sess.findById(id, False)
  HasId = (Err.Number = 0 And Not o Is Nothing)
  Err.Clear
End Function

Sub DismissCommonPopups(sess)
  On Error Resume Next
  Dim n, guard
  guard = 0
  Do While guard < 5
    guard = guard + 1
    If HasId(sess, "wnd[1]/usr/radMULTI_LOGON_OPT2") Then
      sess.findById("wnd[1]/usr/radMULTI_LOGON_OPT2").select
      sess.findById("wnd[1]/tbar[0]/btn[0]").press
    ElseIf HasId(sess, "wnd[1]/tbar[0]/btn[0]") Then
      ' copyright / info — continue carefully only for known info screens
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
  Dim posBtn
  CompanyCodeVisible = False
  ' Position
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

  ' Pattern A — classic V_T001 view maintenance table
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

  ' Pattern B — single-field entry screen
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
