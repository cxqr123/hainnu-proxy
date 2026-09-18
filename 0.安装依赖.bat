@echo off
cd /d "%~dp0"
echo.
echo  Creating the project-local venv and installing dependencies.
echo  (Only needed once, or after the .venv folder is deleted.)
echo.

set "SYSPY="
where python >nul 2>&1 && set "SYSPY=python"
if not defined SYSPY where py >nul 2>&1 && set "SYSPY=py"
if not defined SYSPY (
  echo.
  echo [ERROR] Python not found. Please install Python 3.11+ and add it to PATH, then retry.
  echo.
  pause
  exit /b 1
)

if exist ".venv\Scripts\python.exe" (
  echo  .venv already exists - reusing it.
) else (
  echo  Creating .venv ...
  "%SYSPY%" -m venv .venv
  if errorlevel 1 (
    echo.
    echo [ERROR] Failed to create venv. Install Python 3.11+ and retry.
    echo.
    pause
    exit /b 1
  )
)

echo  Installing runtime deps (fastapi / uvicorn / httpx from requirements.txt) ...
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -i https://pypi.tuna.tsinghua.edu.cn/simple -r requirements.txt
if errorlevel 1 (
  echo.
  echo [ERROR] pip install failed. Check your network and retry.
  echo.
  pause
  exit /b 1
)

echo.
echo  Done. Runtime venv is ~13MB (no playwright).
echo  The token tool (1.get-token.bat) installs playwright on demand, so the baseline stays small.
echo  Now run 2.start-proxy.bat
echo.
pause
