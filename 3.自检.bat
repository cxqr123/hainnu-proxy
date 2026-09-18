@echo off
cd /d "%~dp0"

REM 本机回环必须绕过系统代理：若环境变量里有 HTTP_PROXY（本机 17890 等），
REM urllib/httpx 会把 http://127.0.0.1:8787 也发给它，对方拒代本地地址，直接回 403，
REM 自检就会误报 "Proxy is NOT running"。
set NO_PROXY=localhost,127.0.0.1,::1
set no_proxy=localhost,127.0.0.1,::1

call _find_python.bat
if errorlevel 1 (
  pause
  exit /b 1
)

echo.
echo ============================================================
echo   [0/3] Is the proxy up, and is the school backend OK?
echo ============================================================
"%PY%" -c "import urllib.request,json;d=json.load(urllib.request.urlopen('http://127.0.0.1:8787/health?probe=1',timeout=60));u=d.get('upstream_chat',{});print('  upstream chat :','OK' if u.get('ok') else 'DOWN');print('  detail        :',u.get('detail') or u.get('content') or u.get('error'));print('  hint          :',u.get('hint')) if u.get('hint') else None"
if errorlevel 1 (
  echo.
  echo   Proxy is NOT running. Start 2.start-proxy.bat first.
  echo.
  pause
  exit /b 1
)

echo.
echo ============================================================
echo   [1/3] OpenAI API
echo ============================================================
"%PY%" selftest.py
set RC1=%ERRORLEVEL%

echo.
echo ============================================================
echo   [2/3] Anthropic API
echo ============================================================
"%PY%" test_anthropic.py
set RC2=%ERRORLEVEL%

echo.
echo ============================================================
echo   [3/3] DSH request shape
echo ============================================================
"%PY%" test_dsh.py
set RC3=%ERRORLEVEL%

echo.
echo ============================================================
if "%RC1%"=="0" if "%RC2%"=="0" if "%RC3%"=="0" (
  echo   ALL TESTS PASSED
) else (
  echo   SOME TESTS FAILED   openai=%RC1%  anthropic=%RC2%  dsh=%RC3%
  echo   1. Check http://127.0.0.1:8787/health?probe=1
  echo   2. Re-run 1.get-token.bat if it says 401
  echo   3. See hainnu_proxy.log for details
)
echo ============================================================
echo.
pause
