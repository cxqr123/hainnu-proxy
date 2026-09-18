@echo off
cd /d "%~dp0"
call _find_python.bat
if errorlevel 1 (
  pause
  exit /b 1
)

rem Ensure the token tool's dependency (playwright) is installed. It is
rem NOT part of the runtime (the proxy doesn't need it), so we
rem install it lazily here only when you actually refresh the token.
rem Uses your system-installed Chrome (channel="chrome"), no browser bundled.
"%PY%" -c "import playwright" >nul 2>&1
if errorlevel 1 (
  echo.
  echo  Installing playwright for the token tool (one-time, ~111MB).
  echo  The runtime proxy does NOT need it; you can re-shrink later.
  echo.
  "%PY%" -m pip install --disable-pip-version-check -i https://pypi.tuna.tsinghua.edu.cn/simple playwright
  if errorlevel 1 (
    echo.
    echo [ERROR] playwright install failed. Check your network and retry.
    pause
    exit /b 1
  )
)

echo.
echo  A browser window will open. Log in with your school CAS account.
echo  The token is saved to token.txt automatically.
echo.
echo  Only needed when:
echo    - token.txt is missing
echo    - the proxy reports 401 / auth_expired
echo    - you changed your school password
echo.

"%PY%" get_token.py
echo.
pause
