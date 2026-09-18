' Silent launcher for the local proxy (uses pythonw, no console window).
' Locates its own folder at runtime -> the whole folder is portable to any machine/path.
Set fso = CreateObject("Scripting.FileSystemObject")
base = fso.GetParentFolderName(WScript.ScriptFullName)
Set ws = CreateObject("WScript.Shell")
ws.CurrentDirectory = base
py = base & "\.venv\Scripts\pythonw.exe"
ws.Run """" & py & """ """ & base & "\hainnu_proxy.py""", 0, False
