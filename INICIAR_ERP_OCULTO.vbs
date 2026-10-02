Option Explicit

Dim shell, fso, root, ps1, command
Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

root = fso.GetParentFolderName(WScript.ScriptFullName)
ps1 = fso.BuildPath(root, "SERVIDOR_V3_SIN_VENTANA.ps1")
If Not fso.FileExists(ps1) Then
    WScript.Quit 2
End If

command = "powershell.exe -NoProfile -ExecutionPolicy Bypass -File " & Chr(34) & ps1 & Chr(34)
shell.Run command, 0, False
