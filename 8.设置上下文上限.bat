@echo off
title 设置 DSH 上下文上限
cd /d "%~dp0"
call _find_python.bat
if errorlevel 1 (
  pause
  exit /b 1
)

echo.
echo   ==========================================
echo      设置 DSH 上下文上限
echo   ==========================================
echo.
echo   把 hainnu 模型的 contextWindow 设为 210,000
echo   （学校链路真实可用上限见 README「上下文长度取值」，
echo     取值贴近上限又给溢出救援留一步余量）
echo.
echo   [重要] 请先关闭所有 DSH 窗口再继续，
echo          否则 DSH 回写配置会把改动覆盖掉。
echo.
pause

echo.
echo   正在写入...
echo.
"%PY%" "%~dp0set_context_window.py" --apply

echo.
echo   完成后重启 DSH 生效。
echo.
pause
