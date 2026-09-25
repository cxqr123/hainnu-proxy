@echo off
setlocal enabledelayedexpansion
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

rem 多源按序回退：实测 pip 访问某单个镜像会被 403（curl 同 URL 却正常），
rem 写死一个源会让部分机器怎么装都装不上。
set "INSTALLED=0"
for %%I in ("https://pypi.tuna.tsinghua.edu.cn/simple" "https://mirrors.aliyun.com/pypi/simple" "https://pypi.org/simple") do (
  if "!INSTALLED!"=="0" (
    echo   Trying %%~I ...
    ".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -i "%%~I" -r requirements.txt
    if not errorlevel 1 set "INSTALLED=1"
  )
)
if "!INSTALLED!"=="0" (
  echo.
  echo [ERROR] pip install failed on every mirror.
  echo   Check your network / proxy, then retry. Or just use hainnu-proxy.zip
  echo   from Releases, which bundles runtime\ and needs no install.
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
