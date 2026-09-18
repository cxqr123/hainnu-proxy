@echo off
cd /d "%~dp0"
title 更新 opencode 直连令牌

rem ============================================================
rem  【本脚本只服务于 opencode】
rem  把学校登录 JWT 同步进 opencode 配置的「直连」供应商 hainnu-direct。
rem  其他客户端不使用本脚本：请按 README §8.5「方式二」自行填入 apiKey。
rem
rem  背景：opencode 的自定义 provider 只能在 options.apiKey 里内联密钥
rem  （官方不支持 {env:VAR} / {file:...} 这类取值），所以直连时令牌落在
rem  配置文件里，失效后要有人帮它更新 —— 就是这个脚本。
rem
rem  它做的事：读项目里的 token.txt（DPAPI 加密）→ 解出 JWT →
rem  定点替换 ~/.config/opencode/opencode.jsonc 里 hainnu-direct 的 apiKey
rem  （先备份、写后校验、不过就自动回滚）。
rem
rem  只走桥的 hainnu 供应商不需要跑这个 —— 桥自己读 token.txt。
rem ============================================================

call _find_python.bat
if errorlevel 1 (
  pause
  exit /b 1
)

echo.
echo   ============================================================
echo     更新 opencode「直连」令牌  (hainnu-direct)
echo   ============================================================
echo.

"%PY%" "%~dp0_update_direct_token.py" %*
set "RC=%ERRORLEVEL%"

echo.
if not "%RC%"=="0" (
  echo   [失败] 退出码 %RC%。若提示找不到 token.txt，请先双击「1.获取令牌.bat」。
) else (
  echo   完成。重启 opencode 后生效。
)
echo.
pause
