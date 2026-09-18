@echo off
cd /d "%~dp0"
title 一键配置到 WorkBuddy（经本地服务）

rem ============================================================
rem  一键配置：把海师 DeepSeek 写进 WorkBuddy 的配置文件
rem
rem  链路：经本地服务
rem   · 用之前需要：① 已获取登录令牌（1.获取令牌.bat）② 本地代理正在运行（2.启动代理.bat）
rem  说明：
rem   · 只改 WorkBuddy 的**配置文件**，不动客户端本身，也不写死任何安装位置；
rem   · 配置文件位置自动查找，找不到会请你手动指定（可把文件拖进本窗口）；
rem   · 写前自动备份、写后校验，不过就回滚；重复执行只是更新，不会堆积副本。
rem   · 可选参数：--config "<配置文件路径>"   --dry-run   --yes
rem ============================================================

call "%~dp0..\_find_python.bat"
if errorlevel 1 (
  echo.
  echo   没找到 Python。请确认 runtime\ 目录完整，或跑一次 ..\0.安装依赖.bat
  echo.
  pause
  exit /b 1
)

"%PY%" "%~dp0_setup_agent.py" --agent workbuddy --mode proxy %*
set "RC=%ERRORLEVEL%"

echo.
if not "%RC%"=="0" (
  echo   [未完成] 退出码 %RC%。请按上面的提示补齐条件后再运行。
) else (
  echo   完成。请按上面列出的步骤操作，然后重启 WorkBuddy。
)
echo.
pause
exit /b %RC%
