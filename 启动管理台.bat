@echo off
rem Hainnu DeepSeek proxy - single GUI console.
rem ASCII body on purpose: Chinese in .bat breaks cmd parsing on many locales.
rem The GUI itself (hainnu_gui.py) is Chinese; that is fine.
cd /d "%~dp0"

rem Loopback must bypass any system proxy: if HTTP_PROXY is set (e.g. 127.0.0.1:17890),
rem urllib would also send http://127.0.0.1:<port> through it, and that proxy rejects
rem local addresses with 403 -> the GUI reports "proxy not running" while it is fine.
set NO_PROXY=localhost,127.0.0.1,::1
set no_proxy=localhost,127.0.0.1,::1

rem The GUI needs a Python WITH tkinter (the project .venv usually has none).
rem Prefer no-console launchers, then plain py/python.
set "PY="
where pyw >nul 2>&1 && set "PY=pyw"
if not defined PY where pythonw >nul 2>&1 && set "PY=pythonw"
if not defined PY where py >nul 2>&1 && set "PY=py"
if not defined PY where python >nul 2>&1 && set "PY=python"
if not defined PY (
  echo.
  echo [ERROR] No Python with tkinter was found.
  echo Install standard Python and add it to PATH, or run this:
  echo   python hainnu_gui.py
  echo.
  pause
  exit /b 1
)

echo Starting the management console with %PY% ...
echo The proxy process itself uses the project .venv Python.
start "" %PY% hainnu_gui.py
