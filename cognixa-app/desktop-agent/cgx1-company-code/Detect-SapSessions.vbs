' Cognixa — detect open SAP GUI sessions via COM (works from 32-bit hosts).
' Output lines:
'   SESSION|<conn>|<user>|<client>|<tcode>|<wnd>   (one per session)
'   OK|<connections>|<sessions>                    (summary — parsers look for this)
'   NONE|<reason>|<detail>                         (on failure)
Option Explicit
On Error Resume Next

Dim SapGuiAuto, application, connection, session, info
Dim i, j, nConn, nSess, found, connName, user, client, tcode, wndTitle

found = 0
nConn = 0

Set SapGuiAuto = GetObject("SAPGUI")
If Err.Number <> 0 Or SapGuiAuto Is Nothing Then
  Err.Clear
  Set SapGuiAuto = GetObject("SAPGUISERVER")
End If

If Err.Number <> 0 Or SapGuiAuto Is Nothing Then
  WScript.Echo "NONE|no_sapgui_object|" & Err.Description
  WScript.Quit 2
End If

Err.Clear
Set application = SapGuiAuto.GetScriptingEngine
If Err.Number <> 0 Or application Is Nothing Then
  WScript.Echo "NONE|no_scripting_engine|Enable scripting (Options > Accessibility & Scripting > Scripting) and restart SAP GUI. Err=" & Err.Description
  WScript.Quit 3
End If

On Error Resume Next
nConn = application.Children.Count
If Err.Number <> 0 Then
  WScript.Echo "NONE|children_error|" & Err.Description
  WScript.Quit 4
End If

If nConn = 0 Then
  WScript.Echo "NONE|zero_connections|SAP GUI is open but has 0 scriptable connections. Accept 'A script is trying to access SAP GUI' if prompted. Restart SAP after enabling scripting."
  WScript.Quit 5
End If

For i = 0 To nConn - 1
  Set connection = application.Children(CLng(i))
  If Not connection Is Nothing Then
    On Error Resume Next
    connName = ""
    connName = connection.Description
    If connName = "" Then connName = "conn" & i
    nSess = 0
    nSess = connection.Children.Count
    For j = 0 To nSess - 1
      Set session = connection.Children(CLng(j))
      If Not session Is Nothing Then
        user = ""
        client = ""
        tcode = ""
        wndTitle = ""
        On Error Resume Next
        Set info = session.Info
        If Not info Is Nothing Then
          user = info.User
          client = info.Client
          tcode = info.Transaction
        End If
        Err.Clear
        wndTitle = session.ActiveWindow.Text
        WScript.Echo "SESSION|" & connName & "|" & user & "|" & client & "|" & tcode & "|" & wndTitle
        found = found + 1
      End If
    Next
  End If
Next

If found = 0 Then
  WScript.Echo "NONE|zero_sessions|Connections exist but no sessions. Log on fully to Easy Access."
  WScript.Quit 6
End If

' Summary line last — PowerShell parsers match OK|connections|sessions
WScript.Echo "OK|" & nConn & "|" & found
WScript.Quit 0
