@echo off
cd /d "%~dp0"
call _find_python.bat
if errorlevel 1 (
  pause
  exit /b 1
)

echo.
echo  Registering the proxy as a Windows logon task.
echo  It will then start silently in the background - no console window.
echo.
"%PY%" autostart.py --install
echo.
echo  --- current status ---
"%PY%" autostart.py --status
echo.
pause
