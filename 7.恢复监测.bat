@echo off
title 学校模型恢复监测
cd /d "%~dp0"
call _find_python.bat
if errorlevel 1 (
  pause
  exit /b 1
)

echo.
echo  ============================================================
echo   学校模型恢复监测
echo   每 60 秒通过本地代理探测一次学校后端（8787 必须在运行）。
echo   恢复后会响铃提示；按 Ctrl+C 可随时停止。
echo  ============================================================
echo.

:loop
"%PY%" -c "import urllib.request,json,sys;d=json.load(urllib.request.urlopen('http://127.0.0.1:8787/health?probe=1',timeout=90));sys.exit(0 if d.get('upstream_chat',{}).get('ok') else 2)" >nul 2>&1
if errorlevel 2 goto down
if errorlevel 1 goto proxy_down
goto recovered

:down
echo   [%date% %time%] 仍未恢复：学校上游 402 Payment Required（学校侧问题，等学校处理）...
timeout /t 60 /nobreak >nul
goto loop

:proxy_down
echo.
echo   本地代理没有在运行，探测无从谈起！
echo   请先双击 2.启动代理.bat（黑窗口保持开着），再重新运行本脚本。
echo.
pause
exit /b 1

:recovered
echo.
echo  ============================================================
echo   学校模型已恢复！本地代理正在运行，直接打开 DSH 即可使用。
echo  ============================================================
echo.
rundll32 user32.dll,MessageBeep
pause
