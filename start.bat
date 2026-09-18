@echo off
rem ASCII filename+content on purpose: a Chinese filename breaks when the
rem bat is invoked through a cmd string (encoding), and it is locale-fragile
rem on other machines. This is the safe, universal double-click entry.
cd /d "%~dp0"

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
