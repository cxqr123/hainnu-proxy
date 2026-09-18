@echo off
cd /d "%~dp0"
title 关闭 hainnu 代理

call _find_python.bat
if errorlevel 1 (
  pause
  exit /b 1
)

echo.
echo  ============================================================
echo   关闭本地代理  (释放 8787 端口)
echo  ============================================================
echo.
rem 用 _port_guard.py 精确匹配「本地地址列 = 该端口 且 LISTENING」。
rem 老写法是 netstat ^| findstr :8787 —— 子串匹配会把 127.0.0.1:87870 也算进来，
rem 可能误杀无关进程。
"%PY%" "%~dp0_port_guard.py" free

echo.
echo   提示：关闭后建议等约 30 秒再启动新代理，
echo   避免 Windows 端口 TIME_WAIT 导致启动时报 10048。
echo.
pause
